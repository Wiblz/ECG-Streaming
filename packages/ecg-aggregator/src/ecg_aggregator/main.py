"""Main entry point for the ECG Aggregator."""

import asyncio
import signal
import sys
from pathlib import Path

import uvicorn
from ecg_common.logging import get_logger, setup_logging

from ecg_aggregator.api.data_buffer import ECGDataBuffer
from ecg_aggregator.api.server import ECGStreamingServer
from ecg_aggregator.config import AggregatorSettings
from ecg_aggregator.grpc_server import ECGStreamingServicer
from ecg_aggregator.storage.persistence import ECGDatabase
from ecg_aggregator.sync.time_alignment import TimeAlignmentService

try:
    import grpc
    from ecg_common.proto import ecg_streaming_pb2_grpc
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

        self.data_buffer = ECGDataBuffer(
            duration_seconds=config.buffer.duration_seconds,
            max_samples=config.buffer.max_samples,
        )

        self.database = ECGDatabase(db_path=config.storage.database_path)

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
            data_buffer=self.data_buffer,
            database=self.database,
        )

        ecg_streaming_pb2_grpc.add_ECGStreamingServiceServicer_to_server(
            self.grpc_servicer, self.grpc_server
        )

        listen_addr = f"[::]:{self.config.grpc.port}"
        self.grpc_server.add_insecure_port(listen_addr)

        logger.info(f"Starting gRPC server on {listen_addr}")
        await self.grpc_server.start()

    async def _start_http_server(self) -> None:
        """Start the HTTP/WebSocket server."""
        self.http_server = ECGStreamingServer(
            time_alignment=self.time_alignment,
            data_buffer=self.data_buffer,
            websocket_fps=self.config.api.websocket_fps,
            cors_origins=self.config.api.cors_origins,
        )

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


def main() -> None:
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="ECG Aggregator")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config.yaml"),
        help="Path to configuration file",
    )
    args = parser.parse_args()

    # Load configuration
    try:
        if args.config.exists():
            config = AggregatorSettings.from_yaml(args.config)
        else:
            logger.warning(f"Config file {args.config} not found, using defaults")
            config = AggregatorSettings()
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        sys.exit(1)

    # Setup logging
    setup_logging(
        level=config.logging.level,
        log_file=config.logging.file,
        log_format=config.logging.format,
    )

    # Create and run aggregator
    aggregator = ECGAggregator(config)

    try:
        asyncio.run(aggregator.start())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Aggregator error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
