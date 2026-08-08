"""ECG Aggregator application - core server logic."""

import asyncio
import signal

import grpc
import uvicorn
from ecg_common.logging import get_logger
from ecg_common.proto import collector_aggregator_pb2_grpc

from ecg_aggregator.api.server import APIServer
from ecg_aggregator.application.runtime import ApplicationRuntime
from ecg_aggregator.application.services.buffer_query_service import BufferQueryService
from ecg_aggregator.application.services.calibration_service import CalibrationService
from ecg_aggregator.application.services.collector_query_service import CollectorQueryService
from ecg_aggregator.application.services.device_query_service import DeviceQueryService
from ecg_aggregator.application.services.ingest_service import IngestService
from ecg_aggregator.application.services.runtime_state import CollectorRegistry, DeviceRegistry
from ecg_aggregator.application.services.session_query_service import SessionQueryService
from ecg_aggregator.application.services.session_service import SessionService
from ecg_aggregator.application.services.system_query_service import SystemQueryService
from ecg_aggregator.config import AggregatorSettings
from ecg_aggregator.grpc_server import ECGStreamingServicer
from ecg_aggregator.infrastructure.persistence.sqlite_database import ECGDatabase
from ecg_aggregator.infrastructure.realtime.buffers import (
    AccelerometerDataBuffer,
    ECGDataBuffer,
)
from ecg_aggregator.infrastructure.realtime.calibration_hub import CalibrationWebSocketHub
from ecg_aggregator.infrastructure.realtime.event_bus import InMemoryDomainEventBus
from ecg_aggregator.infrastructure.realtime.realtime_ws_hub import RealtimeWebSocketHub
from ecg_aggregator.infrastructure.realtime.sse_hub import SSEHub
from ecg_aggregator.sync.calibration_manager import CalibrationManager
from ecg_aggregator.sync.time_alignment import TimeAlignmentService

logger = get_logger(__name__)


class ECGAggregator:
    """Main aggregator application."""

    def __init__(self, config: AggregatorSettings):
        self.config = config

        # Infrastructure
        self.time_alignment = TimeAlignmentService(
            window_size=config.sync.window_size,
            min_samples=config.sync.min_samples,
        )
        self.ecg_buffer = ECGDataBuffer(
            duration_seconds=config.buffer.duration_seconds,
            max_samples=config.buffer.max_samples,
        )
        self.acc_buffer = AccelerometerDataBuffer(
            duration_seconds=config.buffer.duration_seconds,
            max_samples=config.buffer.max_samples,
        )
        self.database = ECGDatabase(db_path=config.storage.database_path)
        self.calibration_manager = CalibrationManager(database=self.database)
        self.event_bus = InMemoryDomainEventBus()

        # Application services
        self.collector_registry = CollectorRegistry()
        self.device_registry = DeviceRegistry()
        self.session_service = SessionService(
            database=self.database,
            device_registry=self.device_registry,
        )
        self.ingest_service = IngestService(
            time_alignment=self.time_alignment,
            ecg_buffer=self.ecg_buffer,
            acc_buffer=self.acc_buffer,
            database=self.database,
            calibration_manager=self.calibration_manager,
            event_bus=self.event_bus,
            collector_registry=self.collector_registry,
            device_registry=self.device_registry,
            session_service=self.session_service,
        )
        self.session_service.set_flush_pending_samples(self.ingest_service.flush_samples)

        # gRPC delivery
        self.grpc_servicer = ECGStreamingServicer(self.ingest_service)
        self.grpc_server: grpc.aio.Server | None = None

        # HTTP delivery
        realtime_hub = RealtimeWebSocketHub(
            ecg_buffer=self.ecg_buffer,
            acc_buffer=self.acc_buffer,
            websocket_push_rate_hz=config.api.websocket_push_rate_hz,
        )
        calibration_service = CalibrationService(
            calibration_manager=self.calibration_manager,
            time_alignment=self.time_alignment,
        )
        runtime = ApplicationRuntime(
            ingest_service=self.ingest_service,
            session_service=self.session_service,
            session_query_service=SessionQueryService(database=self.database),
            device_query_service=DeviceQueryService(
                database=self.database,
                time_alignment=self.time_alignment,
                collector_registry=self.collector_registry,
                device_registry=self.device_registry,
            ),
            buffer_query_service=BufferQueryService(
                ecg_buffer=self.ecg_buffer,
                acc_buffer=self.acc_buffer,
            ),
            collector_query_service=CollectorQueryService(
                database=self.database,
                collector_registry=self.collector_registry,
            ),
            system_query_service=SystemQueryService(
                time_alignment=self.time_alignment,
                ecg_buffer=self.ecg_buffer,
                acc_buffer=self.acc_buffer,
                ingest_service=self.ingest_service,
                list_ecg_connections=realtime_hub.list_ecg_connections,
                list_acc_connections=realtime_hub.list_acc_connections,
            ),
            calibration_service=calibration_service,
        )
        self.http_server = APIServer(
            runtime=runtime,
            realtime_hub=realtime_hub,
            sse_hub=SSEHub(self.event_bus),
            calibration_hub=CalibrationWebSocketHub(calibration_service, self.event_bus),
            cors_origins=config.api.cors_origins,
        )
        self.uvicorn_server: uvicorn.Server | None = None

    async def start(self) -> None:
        """Start the aggregator."""
        logger.info("Starting ECG Aggregator...")
        logger.info(f"gRPC port: {self.config.grpc.port}")
        logger.info(f"API port: {self.config.api.port}")
        logger.info(f"Database: {self.config.storage.database_path}")

        await self._start_grpc_server()
        await self._start_http_server()

        logger.info("ECG Aggregator started successfully")

        await self._wait_for_shutdown()

    async def stop(self) -> None:
        """Stop the aggregator."""
        logger.info("Stopping ECG Aggregator...")

        assert self.uvicorn_server is not None
        assert self.grpc_server is not None

        logger.info("Stopping HTTP/WebSocket server...")
        self.uvicorn_server.should_exit = True
        await self.http_server.stop_broadcast()
        await self.http_server.shutdown()

        logger.info("Stopping gRPC server...")
        await self.ingest_service.stop_stats_task()
        await self.ingest_service.stop_flush_task()
        await self.grpc_server.stop(grace=5)

        logger.info("Closing database...")
        self.database.close()

        logger.info("ECG Aggregator stopped")

    async def _start_grpc_server(self) -> None:
        """Start the gRPC server."""
        self.grpc_server = grpc.aio.server()

        collector_aggregator_pb2_grpc.add_ECGStreamingServiceServicer_to_server(
            self.grpc_servicer, self.grpc_server
        )

        listen_addr = f"{self.config.grpc.host}:{self.config.grpc.port}"
        self.grpc_server.add_insecure_port(listen_addr)

        logger.info(f"Starting gRPC server on {listen_addr}")
        await self.grpc_server.start()

        self.ingest_service.start_flush_task()
        self.ingest_service.start_stats_task()

    async def _start_http_server(self) -> None:
        """Start the HTTP/WebSocket server."""
        await self.http_server.start_broadcast()

        uvicorn_config = uvicorn.Config(
            app=self.http_server.app,
            host=self.config.api.host,
            port=self.config.api.port,
            log_level="info",
            log_config=None,
        )
        self.uvicorn_server = uvicorn.Server(uvicorn_config)
        asyncio.create_task(self.uvicorn_server.serve())

        logger.info(f"HTTP/WebSocket server started on port {self.config.api.port}")

    async def _wait_for_shutdown(self) -> None:
        """Wait for shutdown signal."""
        shutdown_event = asyncio.Event()

        def signal_handler() -> None:
            logger.info("Received shutdown signal")
            shutdown_event.set()

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, signal_handler)

        await shutdown_event.wait()
        await self.stop()
