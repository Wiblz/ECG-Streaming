"""Main entry point for the ECG Collector."""

import asyncio
import contextlib
import signal
import sys
from pathlib import Path

from ecg_common.logging import get_logger, setup_logging
from ecg_common.models import DeviceStatus

from ecg_collector.collector.adapter_manager import BLEAdapterManager
from ecg_collector.collector.device_state_manager import DeviceStateManager
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

        self.device_manager = DeviceStateManager(monitor_interval=5.0)

        self.grpc_client = AggregatorClient(
            collector_id=config.collector_id,
            aggregator_host=config.aggregator.host,
            aggregator_port=config.aggregator.port,
            device_ids=config.device_ids,
            display_name=config.display_name,
            batch_size=config.aggregator.batch_size,
            batch_interval=config.aggregator.batch_interval,
        )

        self._running = False
        self._collection_tasks: dict[str, asyncio.Task] = {}

    async def start(self) -> None:
        """Start the collector."""
        logger.info("Starting ECG Collector...")
        logger.info(f"Collector ID: {self.config.collector_id}")
        logger.info(f"Display Name: {self.config.display_name}")
        logger.info(f"Devices: {self.config.device_ids}")
        logger.info(f"Aggregator: {self.config.aggregator.host}:{self.config.aggregator.port}")

        # Connect to aggregator
        if not await self.grpc_client.connect():
            logger.error("Failed to connect to aggregator, exiting")
            return

        # Add devices to adapter manager and state manager
        for device_id in self.config.device_ids:
            try:
                driver = self.adapter_manager.add_device(
                    device_id=device_id,
                    address=None,  # Let driver discover MAC address by device name
                )
                self.device_manager.add_device(driver)
                await self.grpc_client.update_device_status(device_id, DeviceStatus.DISCONNECTED)
            except Exception as e:
                logger.error(f"Failed to add device {device_id}: {e}")

        # Start device state manager (handles connections and reconnections)
        await self.device_manager.start()

        # Start monitoring and sampling
        self._running = True
        self._monitor_task = asyncio.create_task(self._device_monitor_loop())

        logger.info("ECG Collector started successfully")
        logger.info("Device state manager will attempt connections automatically")

        # Wait for shutdown
        await self._wait_for_shutdown()

    async def stop(self) -> None:
        """Stop the collector."""
        logger.info("Stopping ECG Collector...")

        self._running = False

        # Stop monitor task
        if hasattr(self, "_monitor_task"):
            self._monitor_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._monitor_task

        # Cancel all collection tasks
        for task in self._collection_tasks.values():
            task.cancel()

        await asyncio.gather(*self._collection_tasks.values(), return_exceptions=True)
        self._collection_tasks.clear()

        # Stop device state manager
        await self.device_manager.stop()

        # Stop streaming on all devices
        logger.info("Stopping ECG streaming on all devices...")
        await self.adapter_manager.stop_streaming_all()

        # Disconnect devices
        logger.info("Disconnecting devices...")
        await self.adapter_manager.disconnect_all()

        # Disconnect from aggregator
        await self.grpc_client.disconnect()

        logger.info("ECG Collector stopped")

    async def _device_monitor_loop(self) -> None:
        """Monitor device states and manage sampling tasks."""
        logger.info("Device monitor loop started")

        while self._running:
            try:
                # Check each managed device
                for managed_device in self.device_manager.get_all_devices():
                    device_id = managed_device.device_id

                    # Start sampling task if device is streaming and task not running
                    if (
                        managed_device.state.value == "streaming"
                        and device_id not in self._collection_tasks
                    ):
                        logger.info(f"Starting data collection for {device_id}")
                        task = asyncio.create_task(self._data_collection_loop(device_id))
                        self._collection_tasks[device_id] = task
                        logger.info(f"Updating device status to STREAMING for {device_id}")
                        await self.grpc_client.update_device_status(
                            device_id, DeviceStatus.STREAMING
                        )

                    # Stop sampling task if device not streaming but task is running
                    elif (
                        managed_device.state.value != "streaming"
                        and device_id in self._collection_tasks
                    ):
                        logger.info(f"Stopping data collection for {device_id}")
                        task = self._collection_tasks[device_id]
                        task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await task
                        del self._collection_tasks[device_id]

                        # Update status based on device state
                        if managed_device.driver._status == DeviceStatus.DISCONNECTED:
                            await self.grpc_client.update_device_status(
                                device_id, DeviceStatus.DISCONNECTED
                            )
                        elif managed_device.driver._status == DeviceStatus.CONNECTED:
                            await self.grpc_client.update_device_status(
                                device_id, DeviceStatus.CONNECTED
                            )

                # Clean up completed tasks
                completed = [
                    device_id for device_id, task in self._collection_tasks.items() if task.done()
                ]
                for device_id in completed:
                    del self._collection_tasks[device_id]
                    logger.warning(f"Data collection task for {device_id} completed unexpectedly")

                await asyncio.sleep(2.0)  # Check every 2 seconds

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in device monitor loop: {e}")
                await asyncio.sleep(2.0)

        logger.info("Device monitor loop stopped")

    async def _data_collection_loop(self, device_id: str) -> None:
        """Collect ECG and accelerometer samples from a device and send to aggregator.

        Args:
            device_id: Device to collect from
        """
        logger.info(f"Data collection started for {device_id}")

        driver = self.adapter_manager.get_device(device_id)
        if not driver:
            logger.error(f"Device {device_id} not found")
            return

        ecg_sample_count = 0
        acc_sample_count = 0

        try:
            while self._running:
                # Read ECG sample
                ecg_sample = await driver.read_ecg_sample()
                if ecg_sample:
                    await self.grpc_client.send_sample(ecg_sample)
                    ecg_sample_count += 1

                    if ecg_sample_count % 1000 == 0:
                        logger.debug(f"Collected {ecg_sample_count} ECG samples from {device_id}")

                # Read accelerometer sample
                acc_sample = await driver.read_accelerometer_sample()
                if acc_sample:
                    await self.grpc_client.send_acc_sample(acc_sample)
                    acc_sample_count += 1

                    if acc_sample_count % 1000 == 0:
                        logger.debug(f"Collected {acc_sample_count} ACC samples from {device_id}")

                # If no samples available, sleep briefly
                if not ecg_sample and not acc_sample:
                    await asyncio.sleep(0.001)

        except asyncio.CancelledError:
            logger.info(
                f"Data collection stopped for {device_id} "
                f"({ecg_sample_count} ECG, {acc_sample_count} ACC samples)"
            )
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
