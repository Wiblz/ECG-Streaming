"""USB collector data models and enums."""

from dataclasses import dataclass
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
class UsbInterfaceInfo:
    """Information about a USB interface."""

    device_path: str
    interface_type: InterfaceType
    usb_serial: str
    interface_string: str


@dataclass
class EspDeviceGroup:
    """Group of USB interfaces belonging to the same physical ESP device."""

    usb_serial: str
    bus_port: str = ""  # USB bus-port identifier (e.g., "3-1" or "9-1.1")
    data_interface: UsbInterfaceInfo | None = None
    log_interface: UsbInterfaceInfo | None = None
    device_info: dict | None = None
    probe_status: ProbeStatus = ProbeStatus.DISCOVERED
    error_message: str | None = None
