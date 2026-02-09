"""USB collector data models and enums."""

from dataclasses import dataclass, field
from enum import Enum


class InterfaceType(str, Enum):
    """USB interface type based on interface descriptor string."""

    DATA = "DATA"
    LOG = "LOG"
    UNKNOWN = "UNKNOWN"


class ProbeStatus(str, Enum):
    """Status of device probing."""

    DISCOVERED = "DISCOVERED"
    PROBING = "PROBING"
    RECEIVED = "RECEIVED"
    TIMEOUT = "TIMEOUT"
    ERROR = "ERROR"


@dataclass
class UsbCollectorStats:
    """Statistics for USB collector data reception."""

    frames_received: int = 0
    frames_crc_errors: int = 0
    frames_parse_errors: int = 0
    messages_received: int = 0
    bytes_received: int = 0

    def reset(self) -> None:
        """Reset all statistics to zero."""
        self.frames_received = 0
        self.frames_crc_errors = 0
        self.frames_parse_errors = 0
        self.messages_received = 0
        self.bytes_received = 0

    def to_dict(self) -> dict[str, int]:
        """Convert stats to dictionary for serialization."""
        return {
            "frames_received": self.frames_received,
            "frames_crc_errors": self.frames_crc_errors,
            "frames_parse_errors": self.frames_parse_errors,
            "messages_received": self.messages_received,
            "bytes_received": self.bytes_received,
        }


@dataclass
class UsbInterfaceInfo:
    """Information about a USB interface."""

    device_path: str
    interface_type: InterfaceType
    usb_serial: str
    interface_string: str


@dataclass
class EspDeviceInfo:
    """Information about an ESP32 device."""

    esp_id: str
    app_version: str
    idf_version: str
    protocol_version: int
    current_targets: list[str]
    config_required: bool
    polar_connected: bool
    target_status: dict[str, bool] = field(default_factory=dict)


@dataclass
class ProbePartialInfo:
    """Partial probe result when device sends messages but no device_info."""

    last_message_type: str  # e.g., "ecg_frame", "acc_frame"
    device_id: str | None  # Device ID from the message, if available


@dataclass
class EspDeviceGroup:
    """Group of USB interfaces belonging to the same physical ESP device."""

    usb_serial: str
    bus_port: str = ""  # USB bus-port identifier (e.g., "3-1" or "9-1.1")
    data_interface: UsbInterfaceInfo | None = None
    log_interface: UsbInterfaceInfo | None = None
    device_info: EspDeviceInfo | None = None
    probe_status: ProbeStatus = ProbeStatus.DISCOVERED
    error_message: str | None = None
    partial_info: ProbePartialInfo | None = None  # Populated on timeout with partial data
