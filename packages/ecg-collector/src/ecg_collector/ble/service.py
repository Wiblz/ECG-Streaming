"""BLE Collector Service - Integrates BLE devices with gRPC aggregator."""

import asyncio
import contextlib
import signal

from ecg_common.logging import get_logger
from ecg_common.models import DeviceStatus

from ecg_collector.ble.adapter_manager import BLEAdapterManager
from ecg_collector.ble.batcher import SampleBatcher
from ecg_collector.ble.device_state_manager import DeviceStateManager
from ecg_collector.config import CollectorSettings
from ecg_collector.grpc_client import CollectorGrpcClient

logger = get_logger(__name__)


class BleCollectorService:
    """Service that connects BLE devices to gRPC aggregator."""

    def __init__(self, settings: CollectorSettings) -> None:
        """Initialize BLE collector service.

        Args:
            settings: Collector configuration settings
        """
        self.settings = settings
        self.running = False

        # Initialize components
        self.adapter_manager = BLEAdapterManager(
            max_devices_per_adapter=settings.ble.max_devices_per_adapter
        )
        self.device_manager = DeviceStateManager(monitor_interval=5.0)

        # Initialize gRPC client
        self.grpc_client = CollectorGrpcClient(
            collector_id=settings.collector_id,
            aggregator_host=settings.aggregator.host,
            aggregator_port=settings.aggregator.port,
            device_ids=settings.device_ids,
            display_name=settings.display_name,
            metadata={"type": "polar_h10_collector"},
        )

        # Initialize sample batcher
        self.batcher = SampleBatcher(
            device_ids=settings.device_ids,
            batch_size=settings.aggregator.batch_size,
            batch_interval=settings.aggregator.batch_interval,
            message_callback=self.grpc_client.send_message,
        )

        self._collection_tasks: dict[str, asyncio.Task] = {}
        self._monitor_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the BLE collector service."""
        logger.info(f"Starting BLE Collector: {self.settings.collector_id}")
        logger.info(f"Display Name: {self.settings.display_name}")
        logger.info(f"Devices: {self.settings.device_ids}")
        logger.info(f"Aggregator: {self.settings.aggregator.host}:{self.settings.aggregator.port}")

        self.running = True

        # Start batcher
        await self.batcher.start()

        # Start gRPC client
        asyncio.create_task(self.grpc_client.run())

        # Wait for initial connection
        await asyncio.sleep(0.5)
        if not self.grpc_client.connected:
            logger.warning(
                "Initial connection to aggregator failed, but will keep retrying in background"
            )

        # Add devices to adapter manager and state manager
        for device_id in self.settings.device_ids:
            try:
                driver = self.adapter_manager.add_device(
                    device_id=device_id,
                    address=None,  # Let driver discover MAC address by device name
                )
                self.device_manager.add_device(driver)
                await self.batcher.update_device_status(device_id, DeviceStatus.DISCONNECTED)
            except Exception as e:
                logger.error(f"Failed to add device {device_id}: {e}")

        # Start device state manager
        await self.device_manager.start()

        # Start monitoring
        self._monitor_task = asyncio.create_task(self._monitor_loop())

        logger.info("BLE Collector started successfully")

        # Wait for shutdown signal
        await self._wait_for_shutdown()

    async def stop(self) -> None:
        """Stop the BLE collector service."""
        logger.info("Stopping BLE Collector...")
        self.running = False

        # Stop monitor task
        if self._monitor_task:
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

        # Stop streaming and disconnect devices
        await self.adapter_manager.stop_streaming_all()
        await self.adapter_manager.disconnect_all()

        # Stop batcher
        await self.batcher.stop()

        # Disconnect from aggregator
        await self.grpc_client.disconnect()

        logger.info("BLE Collector stopped")

    async def _monitor_loop(self) -> None:
        """Monitor device states and manage sampling tasks."""
        logger.info("Device monitor loop started")

        while self.running:
            try:
                # Check each managed device
                for managed_device in self.device_manager.get_all_devices():
                    device_id = managed_device.device_id

                    # Start sampling task if device is streaming
                    if (
                        managed_device.state.value == "streaming"
                        and device_id not in self._collection_tasks
                    ):
                        logger.info(f"Starting data collection for {device_id}")
                        task = asyncio.create_task(self._data_collection_loop(device_id))
                        self._collection_tasks[device_id] = task
                        await self.batcher.update_device_status(device_id, DeviceStatus.STREAMING)

                    # Stop sampling task if device not streaming
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

                        # Update status
                        if managed_device.driver._status == DeviceStatus.DISCONNECTED:
                            await self.batcher.update_device_status(
                                device_id, DeviceStatus.DISCONNECTED
                            )
                        elif managed_device.driver._status == DeviceStatus.CONNECTED:
                            await self.batcher.update_device_status(
                                device_id, DeviceStatus.CONNECTED
                            )

                # Clean up completed tasks
                completed = [
                    device_id for device_id, task in self._collection_tasks.items() if task.done()
                ]
                for device_id in completed:
                    del self._collection_tasks[device_id]
                    logger.warning(f"Data collection task for {device_id} completed unexpectedly")

                await asyncio.sleep(2.0)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in monitor loop: {e}")
                await asyncio.sleep(2.0)

        logger.info("Device monitor loop stopped")

    async def _data_collection_loop(self, device_id: str) -> None:
        """Collect ECG and accelerometer samples from a device.

        Args:
            device_id: Device to collect from
        """
        logger.info(f"Data collection started for {device_id}")

        driver = self.adapter_manager.get_device(device_id)
        if not driver:
            logger.error(f"Device {device_id} not found")
            return

        ecg_count = 0
        acc_count = 0

        try:
            while self.running:
                # Read ECG sample
                ecg_sample = await driver.read_ecg_sample()
                if ecg_sample:
                    await self.batcher.send_sample(ecg_sample)
                    ecg_count += 1

                    if ecg_count % 1000 == 0:
                        logger.debug(f"Collected {ecg_count} ECG samples from {device_id}")

                # Read accelerometer sample
                acc_sample = await driver.read_accelerometer_sample()
                if acc_sample:
                    await self.batcher.send_acc_sample(acc_sample)
                    acc_count += 1

                    if acc_count % 1000 == 0:
                        logger.debug(f"Collected {acc_count} ACC samples from {device_id}")

                # Sleep if no samples
                if not ecg_sample and not acc_sample:
                    await asyncio.sleep(0.001)

        except asyncio.CancelledError:
            logger.info(
                f"Data collection stopped for {device_id} "
                f"({ecg_count} ECG, {acc_count} ACC samples)"
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

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, signal_handler)

        await shutdown_event.wait()
