"""Main entry point for ECG Streaming application."""

import asyncio
import signal
from pathlib import Path
from types import FrameType

import typer
import uvicorn

from src.api.data_buffer import ECGDataBuffer
from src.api.server import create_app
from src.collector.adapter_manager import BLEAdapterManager
from src.common.logging import get_logger, setup_logging
from src.config.settings import load_settings
from src.storage.persistence import ECGDatabase
from src.sync.time_alignment import TimeAlignmentService

logger = get_logger(__name__)


class ECGStreamingApp:
    """Main application orchestrator."""

    def __init__(self, config_file: Path | None = None):
        """Initialize the application.

        Args:
            config_file: Optional path to configuration file
        """
        # Load settings
        self.settings = load_settings(config_file)

        # Setup logging
        setup_logging(
            level=self.settings.logging.level,
            log_file=self.settings.logging.log_file,
            log_format=self.settings.logging.format,
        )

        logger.info("Initializing ECG Streaming Application")
        logger.info(f"Configuration: {config_file or 'default'}")

        # Initialize components
        self.adapter_manager = BLEAdapterManager(
            max_devices_per_adapter=self.settings.ble.max_devices_per_adapter
        )

        self.time_alignment = TimeAlignmentService(
            window_size=self.settings.sync.regression_window_size,
            min_samples=self.settings.sync.min_samples_for_sync,
            confidence_threshold=self.settings.sync.confidence_threshold,
        )

        self.data_buffer = ECGDataBuffer(duration_seconds=self.settings.api.buffer_duration_seconds)

        # Create API server
        self.app, self.server = create_app(
            adapter_manager=self.adapter_manager,
            time_alignment=self.time_alignment,
            data_buffer=self.data_buffer,
            websocket_fps=self.settings.api.websocket_fps,
            cors_origins=self.settings.api.cors_origins,
        )

        # Add devices
        for device_id in self.settings.device_ids:
            self.adapter_manager.add_device(device_id)
            self.time_alignment.register_device(device_id)
            logger.info(f"Registered device: {device_id}")

        # Initialize database if persistence is enabled
        self.database: ECGDatabase | None = None
        if self.settings.persistence.enabled:
            self.database = ECGDatabase(db_path=self.settings.persistence.db_path)
            logger.info(f"Persistence enabled: {self.settings.persistence.db_path}")

        # Batch buffer for database writes
        self._db_batch: list[tuple[str, float, float, int, float]] = []
        self._batch_size = self.settings.persistence.batch_size

        # Shutdown flag
        self._shutdown_event = asyncio.Event()

        # Track offset version for each device (to detect when offset is recalculated)
        self._offset_versions: dict[str, int] = {}

        # Data collection task
        self._collection_task: asyncio.Task | None = None

    async def _data_collection_loop(self) -> None:
        """Main data collection and synchronization loop."""
        logger.info("Starting data collection loop")

        try:
            while not self._shutdown_event.is_set():
                # Process samples from all devices
                for driver in self.adapter_manager.get_all_devices():
                    # Read ECG samples
                    while True:
                        sample = await driver.read_ecg_sample()
                        if sample is None:
                            break

                        # Add to time alignment
                        self.time_alignment.add_timestamp_pair(
                            sample.device_id,
                            sample.device_timestamp,
                            sample.host_receive_time,
                        )

                        # Synchronize timestamp
                        synced = self.time_alignment.sync_timestamp(
                            sample.device_id, sample.device_timestamp
                        )

                        # Check if offset was recalculated (new version)
                        if synced and self.database is not None:
                            device_model = self.time_alignment._device_models.get(sample.device_id)
                            if device_model and device_model.offset is not None:
                                current_version = device_model.offset_version
                                last_version = self._offset_versions.get(sample.device_id, 0)

                                if current_version > last_version:
                                    # Offset was recalculated! First flush current batch to DB
                                    if self._db_batch:
                                        logger.info(
                                            f"Flushing {len(self._db_batch)} samples before UPDATE (version {last_version} -> {current_version})"
                                        )
                                        self.database.add_samples_batch(self._db_batch)
                                        self._db_batch.clear()

                                    # Now update previous unsynced samples in database
                                    self._offset_versions[sample.device_id] = current_version
                                    logger.info(
                                        f"Running UPDATE for {sample.device_id} with offset {device_model.offset:.3f}"
                                    )
                                    updated_count = self.database.update_unsynced_samples(
                                        device_id=sample.device_id,
                                        offset=device_model.offset,
                                    )
                                    logger.info(
                                        f"UPDATE completed: {updated_count} samples updated"
                                    )

                        # Determine global time and confidence
                        if synced:
                            global_time = synced.global_time
                            confidence = synced.confidence
                        else:
                            # Use host receive time as fallback for unsynced samples
                            global_time = sample.host_receive_time
                            confidence = 0.0

                        # Add to buffer (only synced samples with good confidence)
                        if synced and confidence >= self.settings.sync.confidence_threshold:
                            self.data_buffer.add_sample(
                                device_id=sample.device_id,
                                global_time=global_time,
                                raw_value=sample.raw_value,
                                confidence=confidence,
                            )

                        # Add to database batch if persistence enabled (all samples)
                        if self.database is not None:
                            self._db_batch.append(
                                (
                                    sample.device_id,
                                    global_time,
                                    sample.device_timestamp / 1_000_000.0,  # Convert to seconds
                                    sample.raw_value,
                                    confidence,
                                )
                            )

                            # Flush batch if it reaches batch size
                            if len(self._db_batch) >= self._batch_size:
                                self.database.add_samples_batch(self._db_batch)
                                self._db_batch.clear()

                # Small sleep to avoid busy loop
                await asyncio.sleep(0.001)  # 1ms

        except asyncio.CancelledError:
            logger.info("Data collection loop cancelled")
        except Exception as e:
            logger.error(f"Error in data collection loop: {e}", exc_info=True)
        finally:
            # Flush any remaining batch data
            if self.database is not None and self._db_batch:
                logger.info(f"Flushing {len(self._db_batch)} remaining samples to database")
                self.database.add_samples_batch(self._db_batch)
                self._db_batch.clear()

    async def start(self) -> None:
        """Start the application."""
        logger.info("Starting ECG Streaming Application")

        # Connect to devices
        logger.info(f"Connecting to {len(self.settings.device_ids)} devices...")
        connection_status = await self.adapter_manager.connect_all()

        connected_count = sum(1 for success in connection_status.values() if success)
        logger.info(f"Connected to {connected_count}/{len(self.settings.device_ids)} devices")

        if connected_count == 0:
            logger.error("No devices connected. Exiting.")
            return

        # Start streaming
        logger.info("Starting data streams...")
        streaming_status = await self.adapter_manager.start_streaming_all()

        streaming_count = sum(1 for success in streaming_status.values() if success)
        logger.info(f"Started streaming on {streaming_count}/{connected_count} devices")

        if streaming_count == 0:
            logger.error("No devices streaming. Exiting.")
            await self.adapter_manager.disconnect_all()
            return

        # Start data collection loop
        self._collection_task = asyncio.create_task(self._data_collection_loop())

        # Start WebSocket broadcast
        await self.server.start_broadcast()

        logger.info("Application started successfully")
        logger.info(f"API server: http://{self.settings.api.host}:{self.settings.api.port}")
        logger.info(f"WebSocket: ws://{self.settings.api.host}:{self.settings.api.port}/ws/ecg")

    async def stop(self) -> None:
        """Stop the application gracefully."""
        logger.info("Stopping ECG Streaming Application")

        # Signal shutdown
        self._shutdown_event.set()

        # Stop data collection
        if self._collection_task and not self._collection_task.done():
            self._collection_task.cancel()
            try:
                await self._collection_task
            except asyncio.CancelledError:
                pass

        # Stop server
        await self.server.shutdown()

        # Stop streaming and disconnect devices
        logger.info("Stopping device streams...")
        await self.adapter_manager.stop_streaming_all()

        logger.info("Disconnecting devices...")
        await self.adapter_manager.disconnect_all()

        # Close database
        if self.database is not None:
            self.database.close()

        logger.info("Application stopped")

    def _handle_signal(self, signum: int, frame: FrameType | None) -> None:
        """Handle shutdown signal."""
        logger.info(f"Received signal {signum}")
        asyncio.create_task(self.stop())


# CLI interface
cli = typer.Typer(help="ECG Streaming Server")


@cli.command()
def run(
    config: Path | None = None,
    host: str | None = None,
    port: int | None = None,
) -> None:
    """Run the ECG streaming server."""

    async def run_server() -> None:
        # Create application
        app_instance = ECGStreamingApp(config_file=config)

        # Override settings if provided
        if host:
            app_instance.settings.api.host = host
        if port:
            app_instance.settings.api.port = port

        # Setup signal handlers
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(app_instance.stop()))

        try:
            # Start application
            await app_instance.start()

            # Run FastAPI server
            uvicorn_config = uvicorn.Config(
                app_instance.app,
                host=app_instance.settings.api.host,
                port=app_instance.settings.api.port,
                log_level=app_instance.settings.logging.level.lower(),
            )
            server = uvicorn.Server(uvicorn_config)

            # Run server (this blocks)
            await server.serve()

        except Exception as e:
            logger.error(f"Application error: {e}", exc_info=True)
        finally:
            await app_instance.stop()

    asyncio.run(run_server())


@cli.command()
def mock(
    config: Path | None = None,
    num_devices: int = 5,
) -> None:
    """Run with mock devices for testing (without real hardware)."""
    typer.echo(f"Running with {num_devices} mock devices")
    typer.echo("[yellow]Mock mode not yet implemented[/yellow]")
    typer.echo("This will simulate device data without requiring real Polar H10 devices")


def main() -> None:
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()
