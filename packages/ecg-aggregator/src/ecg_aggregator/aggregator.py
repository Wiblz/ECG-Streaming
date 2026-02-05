"""ECG Aggregator application - core server logic."""

import asyncio
import signal

import uvicorn
from ecg_common.logging import get_logger

from ecg_aggregator.api.data_buffer import AccelerometerDataBuffer, ECGDataBuffer
from ecg_aggregator.api.server import ECGStreamingServer
from ecg_aggregator.api.sse_broadcaster import SSEBroadcaster
from ecg_aggregator.config import AggregatorSettings
from ecg_aggregator.grpc_server import ECGStreamingServicer
from ecg_aggregator.storage.persistence import ECGDatabase
from ecg_aggregator.sync.calibration_manager import CalibrationManager
from ecg_aggregator.sync.time_alignment import TimeAlignmentService

try:
    import grpc
    from ecg_common.proto import collector_aggregator_pb2_grpc
except ImportError:
    grpc = None

logger = get_logger(__name__)


class ECGAggregator:
    """Main aggregator application."""

    def __init__(self, config: AggregatorSettings):
        """Initialize the aggregator.

        Args:
            config: Aggregator configuration
        """
        self.config = config

        # Initialize components
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

        # Calibration manager for device alignment
        self.calibration_manager = CalibrationManager(database=self.database)

        # SSE broadcaster (shared between gRPC and HTTP servers)
        self.sse_broadcaster = SSEBroadcaster()

        # gRPC server
        self.grpc_server: grpc.aio.Server | None = None
        self.grpc_servicer: ECGStreamingServicer | None = None

        # HTTP/WebSocket server
        self.http_server: ECGStreamingServer | None = None
        self.uvicorn_server: uvicorn.Server | None = None

        self._running = False

    async def start(self) -> None:
        """Start the aggregator."""
        logger.info("Starting ECG Aggregator...")
        logger.info(f"gRPC port: {self.config.grpc.port}")
        logger.info(f"API port: {self.config.api.port}")
        logger.info(f"Database: {self.config.storage.database_path}")

        # Start gRPC server
        await self._start_grpc_server()

        # Start HTTP/WebSocket server
        await self._start_http_server()

        self._running = True
        logger.info("ECG Aggregator started successfully")

        # Wait for shutdown
        await self._wait_for_shutdown()

    async def stop(self) -> None:
        """Stop the aggregator."""
        logger.info("Stopping ECG Aggregator...")

        self._running = False

        # Stop HTTP server
        if self.uvicorn_server:
            logger.info("Stopping HTTP/WebSocket server...")
            self.uvicorn_server.should_exit = True

        # Stop gRPC server
        if self.grpc_server:
            logger.info("Stopping gRPC server...")

            # Stop periodic flush task and flush remaining samples
            if self.grpc_servicer:
                await self.grpc_servicer.stop_flush_task()

            await self.grpc_server.stop(grace=5)

        # Close database
        logger.info("Closing database...")
        self.database.close()

        logger.info("ECG Aggregator stopped")

    async def _start_grpc_server(self) -> None:
        """Start the gRPC server."""
        if grpc is None:
            logger.error("grpc package not available, cannot start gRPC server")
            return

        self.grpc_server = grpc.aio.server()

        self.grpc_servicer = ECGStreamingServicer(
            time_alignment=self.time_alignment,
            ecg_buffer=self.ecg_buffer,
            acc_buffer=self.acc_buffer,
            database=self.database,
            calibration_manager=self.calibration_manager,
            sse_broadcaster=self.sse_broadcaster,
            http_server=None,  # Will be set after HTTP server is created
        )

        collector_aggregator_pb2_grpc.add_ECGStreamingServiceServicer_to_server(
            self.grpc_servicer, self.grpc_server
        )

        # Listen on all interfaces - [::]  accepts both IPv4 and IPv6
        listen_addr = f"[::]:{self.config.grpc.port}"
        self.grpc_server.add_insecure_port(listen_addr)

        logger.info(f"Starting gRPC server on {listen_addr}")
        await self.grpc_server.start()

        # Start periodic flush task for batched database writes
        self.grpc_servicer.start_flush_task()

    async def _start_http_server(self) -> None:
        """Start the HTTP/WebSocket server."""
        self.http_server = ECGStreamingServer(
            time_alignment=self.time_alignment,
            ecg_buffer=self.ecg_buffer,
            acc_buffer=self.acc_buffer,
            database=self.database,
            grpc_servicer=self.grpc_servicer,
            calibration_manager=self.calibration_manager,
            sse_broadcaster=self.sse_broadcaster,
            websocket_fps=self.config.api.websocket_fps,
            cors_origins=self.config.api.cors_origins,
        )

        # Set HTTP server reference in gRPC servicer for calibration broadcasts
        if self.grpc_servicer:
            self.grpc_servicer.http_server = self.http_server

        # Start the WebSocket broadcast task
        await self.http_server.start_broadcast()

        # Configure uvicorn
        uvicorn_config = uvicorn.Config(
            app=self.http_server.app,
            host="0.0.0.0",
            port=self.config.api.port,
            log_level="info",
        )

        self.uvicorn_server = uvicorn.Server(uvicorn_config)

        # Start uvicorn in background
        asyncio.create_task(self.uvicorn_server.serve())

        logger.info(f"HTTP/WebSocket server started on port {self.config.api.port}")

    async def _wait_for_shutdown(self) -> None:
        """Wait for shutdown signal."""
        shutdown_event = asyncio.Event()

        def signal_handler() -> None:
            logger.info("Received shutdown signal")
            shutdown_event.set()

        # Register signal handlers
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, signal_handler)

        # Wait for shutdown event
        await shutdown_event.wait()

        # Trigger stop
        await self.stop()


# Entry point moved to cli.py
