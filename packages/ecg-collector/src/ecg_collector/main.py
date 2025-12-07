"""Main entry point for the ECG Collector."""

import asyncio
import signal
import sys
from pathlib import Path

from ecg_common.logging import get_logger, setup_logging

from ecg_collector.collector.adapter_manager import BLEAdapterManager
from ecg_collector.config import CollectorSettings
from ecg_collector.grpc_client import AggregatorClient

logger = get_logger(__name__)


class ECGCollector:
    """Main collector application."""

    def __init__(self, config: CollectorSettings):
        """Initialize the collector.

        Args:
            config: Collector configuration
        """
        self.config = config

        # Initialize components
        self.adapter_manager = BLEAdapterManager(
            max_devices_per_adapter=config.ble.max_devices_per_adapter
        )

        self.grpc_client = AggregatorClient(
            collector_id=config.collector_id,
            aggregator_host=config.aggregator.host,
            aggregator_port=config.aggregator.port,
            device_ids=config.device_ids,
            batch_size=config.aggregator.batch_size,
            batch_interval=config.aggregator.batch_interval,
        )

        self._running = False
        self._collection_tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        """Start the collector."""
        logger.info("Starting ECG Collector...")
        logger.info(f"Collector ID: {self.config.collector_id}")
        logger.info(f"Devices: {self.config.device_ids}")
        logger.info(f"Aggregator: {self.config.aggregator.host}:{self.config.aggregator.port}")

        # Connect to aggregator
        if not await self.grpc_client.connect():
            logger.error("Failed to connect to aggregator, exiting")
            return

        # Register and connect devices
        for device_id in self.config.device_ids:
            try:
                self.adapter_manager.add_device(
                    device_id=device_id,
                    address=None,  # Let driver discover MAC address by device name
                )
            except Exception as e:
                logger.error(f"Failed to add device {device_id}: {e}")

        # Connect all devices
        logger.info("Connecting to devices...")
        await self.adapter_manager.connect_all()

        # Start streaming on all devices
        logger.info("Starting ECG streaming on all devices...")
        await self.adapter_manager.start_streaming_all()

        # Start data collection loops
        self._running = True
        for device_id in self.config.device_ids:
            task = asyncio.create_task(self._data_collection_loop(device_id))
            self._collection_tasks.append(task)

        logger.info("ECG Collector started successfully")

        # Wait for shutdown
        await self._wait_for_shutdown()

    async def stop(self) -> None:
        """Stop the collector."""
        logger.info("Stopping ECG Collector...")

        self._running = False

        # Cancel collection tasks
        for task in self._collection_tasks:
            task.cancel()

        await asyncio.gather(*self._collection_tasks, return_exceptions=True)

        # Stop streaming on all devices
        logger.info("Stopping ECG streaming on all devices...")
        await self.adapter_manager.stop_streaming_all()

        # Disconnect devices
        logger.info("Disconnecting devices...")
        await self.adapter_manager.disconnect_all()

        # Disconnect from aggregator
        await self.grpc_client.disconnect()

        logger.info("ECG Collector stopped")

    async def _data_collection_loop(self, device_id: str) -> None:
        """Collect ECG samples from a device and send to aggregator.

        Args:
            device_id: Device to collect from
        """
        logger.info(f"Starting data collection for {device_id}")

        driver = self.adapter_manager.get_device(device_id)
        if not driver:
            logger.error(f"Device {device_id} not found")
            return

        sample_count = 0

        try:
            while self._running:
                # Read ECG sample
                sample = await driver.read_ecg_sample()

                if sample:
                    # Send to aggregator
                    await self.grpc_client.send_sample(sample)
                    sample_count += 1

                    if sample_count % 1000 == 0:
                        logger.debug(f"Collected {sample_count} samples from {device_id}")
                else:
                    # No sample available, sleep briefly
                    await asyncio.sleep(0.001)

        except asyncio.CancelledError:
            logger.info(f"Data collection cancelled for {device_id}")
            raise

        except Exception as e:
            logger.error(f"Error in data collection loop for {device_id}: {e}")

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


def main() -> None:
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="ECG Collector")
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
            config = CollectorSettings.from_yaml(args.config)
        else:
            logger.warning(f"Config file {args.config} not found, using defaults")
            config = CollectorSettings()
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        sys.exit(1)

    # Setup logging
    setup_logging(
        level=config.logging.level,
        log_file=config.logging.file,
        log_format=config.logging.format,
    )

    # Validate configuration
    if not config.device_ids:
        logger.error("No devices configured. Please add device_ids to config.yaml")
        sys.exit(1)

    # Create and run collector
    collector = ECGCollector(config)

    try:
        asyncio.run(collector.start())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Collector error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
