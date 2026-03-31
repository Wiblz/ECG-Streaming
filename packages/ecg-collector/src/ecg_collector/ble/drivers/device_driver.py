"""Abstract device driver interface for ECG devices."""

from abc import ABC, abstractmethod
from collections.abc import Mapping

from ecg_common.models import DeviceStatusCode, SensorFrame


class DeviceDriver(ABC):
    """Abstract base class for all device drivers.

    This interface ensures hardware-agnostic operation and allows
    future replacement of devices without architectural changes.
    """

    def __init__(self, device_id: str, adapter_id: str | None = None):
        """Initialize the device driver.

        Args:
            device_id: Unique identifier for this device
            adapter_id: Optional BLE adapter ID (e.g., "hci0", "hci1")
        """
        self.device_id = device_id
        self.adapter_id = adapter_id
        self._status = DeviceStatusCode.DISCONNECTED

    @abstractmethod
    async def connect(self) -> bool:
        """Connect to the device.

        Returns:
            True if connection successful, False otherwise
        """
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from the device."""
        pass

    @abstractmethod
    async def start_streaming(self) -> bool:
        """Start streaming ECG data from the device.

        Returns:
            True if streaming started successfully, False otherwise
        """
        pass

    @abstractmethod
    async def stop_streaming(self) -> None:
        """Stop streaming ECG data from the device."""
        pass

    @abstractmethod
    async def read_frame(self) -> SensorFrame | None:
        """Read a single sensor frame from the device (ECG or ACC).

        Returns:
            SensorFrame if data available, None otherwise
        """
        pass

    @property
    def status(self) -> DeviceStatusCode:
        """Get the current device status.

        Returns:
            Current DeviceStatusCode
        """
        return self._status

    @abstractmethod
    async def get_battery_level(self) -> int | None:
        """Get the device battery level.

        Returns:
            Battery level percentage (0-100) or None if unavailable
        """
        pass

    @abstractmethod
    async def get_device_info(self) -> Mapping[str, object]:
        """Get device information.

        Returns:
            Dictionary containing device information (model, firmware, etc.)
        """
        pass
