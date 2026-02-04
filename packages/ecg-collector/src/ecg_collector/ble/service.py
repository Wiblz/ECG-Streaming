"""BLE Collector Service - Integrates BLE devices with gRPC aggregator."""

import asyncio
import contextlib
import signal

from ecg_common.logging import get_logger
from ecg_common.models import DeviceStatus

from ecg_collector.base import DataCollector
from ecg_collector.ble.adapter_manager import BLEAdapterManager
from ecg_collector.ble.device_state_manager import DeviceStateManager
from ecg_collector.config import CollectorSettings
from ecg_collector.grpc_client import CollectorGrpcClient

logger = get_logger(__name__)


class BleCollectorService(DataCollector):
    """Service that connects BLE devices to gRPC aggregator."""

    def __init__(self, settings: CollectorSettings) -> None:
        """Initialize BLE collector service.

        Args:
            settings: Collector configuration settings
        """
        # Get device list from new unified config
        device_list = settings.get_device_list()

        # Initialize gRPC client
        grpc_client = CollectorGrpcClient(
            collector_id=settings.collector_id,
            aggregator_host=settings.aggregator.host,
            aggregator_port=settings.aggregator.port,
            device_ids=device_list,
            display_name=settings.display_name,
            metadata={"type": "polar_h10_collector"},
        )

        # Initialize base class
        super().__init__(grpc_client)

        self.settings = settings
        self.running = False

        # Initialize BLE-specific components
        self.adapter_manager = BLEAdapterManager(
            max_devices_per_adapter=settings.ble.max_devices_per_adapter
        )
        self.device_manager = DeviceStateManager(monitor_interval=5.0)

        self._collection_tasks: dict[str, asyncio.Task] = {}
        self._monitor_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the BLE collector service."""
        device_list = self.settings.get_device_list()

        logger.info(f"Starting BLE Collector: {self.settings.collector_id}")
        logger.info(f"Display Name: {self.settings.display_name}")
        logger.info(f"Devices: {device_list}")
        logger.info(f"Aggregator: {self.settings.aggregator.host}:{self.settings.aggregator.port}")

        self.running = True

        # Start gRPC client
        asyncio.create_task(self.grpc_client.run())

        # Wait for initial connection
        await asyncio.sleep(0.5)
        if not self.grpc_client.connected:
            logger.warning(
                "Initial connection to aggregator failed, but will keep retrying in background"
            )

        # Add devices to adapter manager and state manager
        for device_id, device_config in self.settings.devices.items():
            if not device_config.enabled:
                logger.info(f"Skipping disabled device: {device_id}")
                continue

            try:
                driver = self.adapter_manager.add_device(
                    device_id=device_id,
                    address=None,  # Let driver discover MAC address by device name
                    adapter_id=device_config.ble_adapter,  # Use pinned adapter if specified
                )
                self.device_manager.add_device(driver)
                await self.send_status_update(device_id, DeviceStatus.DISCONNECTED)

                # Log device nickname if set
                if device_config.nickname:
                    logger.info(f"  {device_id} (nickname: {device_config.nickname})")

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
                        await self.send_status_update(device_id, DeviceStatus.STREAMING)

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
                            await self.send_status_update(device_id, DeviceStatus.DISCONNECTED)
                        elif managed_device.driver._status == DeviceStatus.CONNECTED:
                            await self.send_status_update(device_id, DeviceStatus.CONNECTED)

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
        """Collect raw sensor frames from a device and send to aggregator.

        Args:
            device_id: Device to collect from
        """
        logger.info(f"Data collection started for {device_id}")

        driver = self.adapter_manager.get_device(device_id)
        if not driver:
            logger.error(f"Device {device_id} not found")
            return

        frame_count = 0

        try:
            while self.running:
                # Read raw frame (ECG or ACC)
                raw_frame = await driver.read_frame()
                if raw_frame:
                    # Send frame using base class method (handles conversion + sending)
                    try:
                        await self.send_frame_batch(raw_frame)
                        frame_count += 1

                        if frame_count % 100 == 0:
                            logger.debug(
                                f"Sent {frame_count} frames from {device_id} "
                                f"(type: {raw_frame.sensor_type.value})"
                            )
                    except Exception as e:
                        logger.error(f"Error converting/sending frame from {device_id}: {e}")
                else:
                    # Sleep if no frames available
                    await asyncio.sleep(0.001)

        except asyncio.CancelledError:
            logger.info(f"Data collection stopped for {device_id} ({frame_count} frames)")
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
