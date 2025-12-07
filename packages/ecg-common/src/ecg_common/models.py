"""Shared data models for ECG-Streaming."""

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


@dataclass
class SyncedTimestamp:
    """A timestamp that has been synchronized to global time."""

    global_time: float  # Synchronized global timestamp (seconds since epoch)
    confidence: float  # Confidence in the synchronization (0.0 to 1.0)
    offset_version: int  # Version of the offset calculation used


@dataclass
class BufferedECGSample:
    """ECG sample with synchronized timestamp for buffering."""

    device_id: str
    global_time: float  # Synchronized global timestamp
    raw_value: int
    confidence: float  # Synchronization confidence
