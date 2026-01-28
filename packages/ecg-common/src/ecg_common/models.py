"""Shared data models for ECG-Streaming."""

from dataclasses import dataclass
from enum import Enum


class DeviceStatus(Enum):
    """Device connection status (maps to protobuf enum values)."""

    UNKNOWN = 0
    DISCONNECTED = 1
    CONNECTING = 2
    CONNECTED = 3
    STREAMING = 4
    ERROR = 5


class SensorType(Enum):
    """Type of sensor data.

    Values match the proto enum for easy conversion.
    """

    ECG = 0
    ACCELEROMETER = 1


@dataclass
class SensorFrame:
    """Raw sensor frame from Polar device (unparsed).

    This is the unified transport model used by both BLE and USB collectors.
    The frame contains raw PMD (Polar Measurement Data) bytes that will be
    parsed by the collector service.

    Structure matches esp_collector_pb2.SensorFrame exactly.
    """

    device_id: str  # Polar device ID
    sensor_type: SensorType  # Type of data (ECG or ACC)
    polar_clock_us: int  # Polar device clock - microseconds since Polar boot (last sample)
    receiver_clock_us: (
        int  # Receiver device clock - microseconds since receiver boot (ESP32 or collector)
    )
    wall_clock_us: int  # Wall clock (epoch time) when received by collector (microseconds)
    sample_rate: int  # Sample rate in Hz
    raw_data: bytes  # Raw PMD frame data (unparsed)


@dataclass
class SyncedTimestamp:
    """A timestamp that has been synchronized to global time."""

    global_time: float  # Synchronized global timestamp (seconds since epoch)
    confidence: float  # Confidence in the synchronization (0.0 to 1.0)
    offset_version: int  # Version of the offset calculation used


@dataclass
class BufferedSample:
    """Base class for buffered sensor samples with synchronized timestamps.

    All buffered samples share these common fields for time synchronization
    and device identification.
    """

    id: str  # Unique sample ID (device_id:polar_clock_us for real-time, db ID for historical)
    device_id: str
    global_time: float  # Synchronized global timestamp (seconds since epoch)
    confidence: float  # Synchronization confidence (0.0 to 1.0)
    wall_clock_us: int  # Wall clock (epoch time) when collector received frame (microseconds)
    receiver_clock_us: int  # Receiver device clock (microseconds since ESP32/collector boot)


@dataclass
class BufferedECGSample(BufferedSample):
    """Individual ECG sample with synchronized timestamp for buffering."""

    raw_value: int  # Raw ECG sample value from device


@dataclass
class BufferedAccelerometerSample(BufferedSample):
    """Individual accelerometer sample with synchronized timestamp for buffering."""

    x: float  # X-axis acceleration (g)
    y: float  # Y-axis acceleration (g)
    z: float  # Z-axis acceleration (g)
    magnitude: float  # Total acceleration magnitude: sqrt(x² + y² + z²) in g
