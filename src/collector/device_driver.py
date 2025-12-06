"""Abstract device driver interface for ECG devices."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum


class DeviceStatus(Enum):
    """Device connection status."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    STREAMING = "streaming"
    ERROR = "error"


@dataclass
class ECGSample:
    """A single ECG sample with metadata."""

    device_id: str
    device_timestamp: float  # Device's internal timestamp (microseconds)
    host_receive_time: float  # Host system time when received (seconds since epoch)
    raw_value: int  # Raw ECG value from device
    sample_rate: int  # Sample rate in Hz


@dataclass
class AccelerometerSample:
    """A single accelerometer sample with metadata."""

    device_id: str
    device_timestamp: float
    host_receive_time: float
    x: float
    y: float
    z: float


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
        self._status = DeviceStatus.DISCONNECTED

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
    async def read_ecg_sample(self) -> ECGSample | None:
        """Read a single ECG sample from the device.

        Returns:
            ECGSample if data available, None otherwise
        """
        pass

    @abstractmethod
    async def read_accelerometer_sample(self) -> AccelerometerSample | None:
        """Read a single accelerometer sample from the device.

        Returns:
            AccelerometerSample if data available, None otherwise
        """
        pass

    @property
    def status(self) -> DeviceStatus:
        """Get the current device status.

        Returns:
            Current DeviceStatus
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
    async def get_device_info(self) -> dict:
        """Get device information.

        Returns:
            Dictionary containing device information (model, firmware, etc.)
        """
        pass
