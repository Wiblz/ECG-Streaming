"""BLE adapter manager for handling multiple BLE adapters."""

import asyncio

from ecg_common.logging import get_logger

from ecg_collector.ble.drivers import DeviceDriver, PolarH10Driver
from ecg_collector.ble.types import AdapterStats

logger = get_logger(__name__)


class BLEAdapterManager:
    """Manages multiple BLE adapters and device distribution.

    Distributes devices across multiple BLE adapters (hci0, hci1, etc.)
    to overcome the ~7 device per adapter limitation.
    """

    def __init__(self, max_devices_per_adapter: int = 7):
        """Initialize the adapter manager.

        Args:
            max_devices_per_adapter: Maximum devices per BLE adapter
        """
        self.max_devices_per_adapter = max_devices_per_adapter
        self._adapters: dict[str, list[DeviceDriver]] = {}
        self._devices: dict[str, DeviceDriver] = {}

    def _get_available_adapter(self) -> str | None:
        """Find an adapter with capacity for another device.

        Returns:
            Adapter ID (e.g., "hci0") or None if all full
        """
        # Check existing adapters
        for adapter_id, devices in self._adapters.items():
            if len(devices) < self.max_devices_per_adapter:
                return adapter_id

        # All adapters full, try to add a new one
        adapter_index = len(self._adapters)
        new_adapter = f"hci{adapter_index}"

        # In production, should verify adapter exists
        # For now, just add it to the list
        logger.info(f"Allocating new adapter: {new_adapter}")
        self._adapters[new_adapter] = []
        return new_adapter

    def add_device(
        self,
        device_id: str,
        address: str | None = None,
        adapter_id: str | None = None,
    ) -> DeviceDriver:
        """Add a device to be managed.

        Args:
            device_id: Unique device identifier
            address: Optional BLE address or device name
            adapter_id: Optional specific adapter to use

        Returns:
            Created DeviceDriver instance
        """
        # If device already exists, return it
        if device_id in self._devices:
            logger.warning(f"Device {device_id} already added")
            return self._devices[device_id]

        # Determine which adapter to use
        if adapter_id is None:
            adapter_id = self._get_available_adapter()
            if adapter_id is None:
                raise RuntimeError("No available BLE adapters with capacity")

        # Ensure adapter exists in tracking
        if adapter_id not in self._adapters:
            self._adapters[adapter_id] = []

        # Check adapter capacity
        if len(self._adapters[adapter_id]) >= self.max_devices_per_adapter:
            raise RuntimeError(f"Adapter {adapter_id} is at capacity")

        # Create device driver (Polar H10 for now)
        driver = PolarH10Driver(
            device_id=device_id,
            address=address,
            adapter_id=adapter_id,
        )

        # Track device
        self._adapters[adapter_id].append(driver)
        self._devices[device_id] = driver

        logger.info(
            f"Added device {device_id} to adapter {adapter_id} "
            f"({len(self._adapters[adapter_id])}/{self.max_devices_per_adapter})"
        )

        return driver

    def get_device(self, device_id: str) -> DeviceDriver | None:
        """Get a device by ID.

        Args:
            device_id: Device identifier

        Returns:
            DeviceDriver instance or None if not found
        """
        return self._devices.get(device_id)

    def get_all_devices(self) -> list[DeviceDriver]:
        """Get all managed devices.

        Returns:
            List of all DeviceDriver instances
        """
        return list(self._devices.values())

    def get_devices_by_adapter(self, adapter_id: str) -> list[DeviceDriver]:
        """Get all devices on a specific adapter.

        Args:
            adapter_id: Adapter ID (e.g., "hci0")

        Returns:
            List of DeviceDriver instances on that adapter
        """
        return self._adapters.get(adapter_id, [])

    def get_adapter_stats(self) -> dict[str, AdapterStats]:
        """Get statistics for all adapters.

        Returns:
            Dictionary mapping adapter IDs to their stats
        """
        stats: dict[str, AdapterStats] = {}
        for adapter_id, devices in self._adapters.items():
            stats[adapter_id] = {
                "device_count": len(devices),
                "capacity": self.max_devices_per_adapter,
                "utilization": len(devices) / self.max_devices_per_adapter,
                "devices": [d.device_id for d in devices],
            }
        return stats

    async def connect_all(self) -> dict[str, bool]:
        """Connect all devices concurrently.

        Returns:
            Dictionary mapping device IDs to connection success status
        """
        logger.info(f"Connecting {len(self._devices)} devices...")

        tasks = []
        device_ids = []

        for device_id, driver in self._devices.items():
            tasks.append(driver.connect())
            device_ids.append(device_id)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Map results back to device IDs
        connection_status: dict[str, bool] = {}
        for device_id, result in zip(device_ids, results, strict=True):
            if isinstance(result, Exception):
                logger.error(f"Error connecting {device_id}: {result}")
                connection_status[device_id] = False
            else:
                connection_status[device_id] = bool(result)

        successful = sum(1 for success in connection_status.values() if success)
        logger.info(f"Connected {successful}/{len(self._devices)} devices")

        return connection_status

    async def disconnect_all(self) -> None:
        """Disconnect all devices."""
        logger.info(f"Disconnecting {len(self._devices)} devices...")

        tasks = [driver.disconnect() for driver in self._devices.values()]
        await asyncio.gather(*tasks, return_exceptions=True)

        logger.info("All devices disconnected")

    async def start_streaming_all(self) -> dict[str, bool]:
        """Start streaming on all connected devices.

        Returns:
            Dictionary mapping device IDs to streaming start success status
        """
        logger.info(f"Starting streaming on {len(self._devices)} devices...")

        tasks = []
        device_ids = []

        for device_id, driver in self._devices.items():
            tasks.append(driver.start_streaming())
            device_ids.append(device_id)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        streaming_status: dict[str, bool] = {}
        for device_id, result in zip(device_ids, results, strict=True):
            if isinstance(result, Exception):
                logger.error(f"Error starting streaming {device_id}: {result}")
                streaming_status[device_id] = False
            else:
                streaming_status[device_id] = bool(result)

        successful = sum(1 for success in streaming_status.values() if success)
        logger.info(f"Started streaming on {successful}/{len(self._devices)} devices")

        return streaming_status

    async def stop_streaming_all(self) -> None:
        """Stop streaming on all devices."""
        logger.info(f"Stopping streaming on {len(self._devices)} devices...")

        tasks = [driver.stop_streaming() for driver in self._devices.values()]
        await asyncio.gather(*tasks, return_exceptions=True)

        logger.info("Stopped streaming on all devices")

    def remove_device(self, device_id: str) -> bool:
        """Remove a device from management.

        Args:
            device_id: Device identifier

        Returns:
            True if device was removed, False if not found
        """
        driver = self._devices.get(device_id)
        if not driver:
            return False

        # Remove from adapter tracking
        if driver.adapter_id in self._adapters:
            self._adapters[driver.adapter_id].remove(driver)

        # Remove from devices dict
        del self._devices[device_id]

        logger.info(f"Removed device {device_id}")
        return True
