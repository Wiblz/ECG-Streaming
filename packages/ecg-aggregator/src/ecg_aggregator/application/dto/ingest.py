"""Typed DTOs for collector ingest workflows."""

from dataclasses import dataclass

from ecg_common import DeviceStatus

from ecg_aggregator.domain.time import (
    DeviceTimestampUs,
    OffsetSeconds,
    ReceiverClockUs,
    WallClockUs,
)


@dataclass(frozen=True)
class CollectorRegistrationDTO:
    """Collector registration payload."""

    collector_id: str
    display_name: str
    device_ids: list[str]
    version: str
    metadata: dict[str, str]
    device_nicknames: dict[str, str]


@dataclass(frozen=True)
class RegistrationAckDTO:
    """Collector registration acknowledgement."""

    accepted: bool
    message: str
    server_time_ms: int


@dataclass(frozen=True)
class SyncStatusDTO:
    """Time synchronization update for a device."""

    device_id: str
    sync_ready: bool
    offset_s: OffsetSeconds
    offset_version: int
    confidence: float


@dataclass(frozen=True)
class ECGSampleInDTO:
    """Single ECG sample from the collector transport."""

    value: int
    wall_clock_us: WallClockUs
    polar_clock_us: DeviceTimestampUs
    receiver_clock_us: ReceiverClockUs
    time_verified: bool


@dataclass(frozen=True)
class ECGBatchInDTO:
    """ECG batch from the collector transport."""

    device_id: str
    sample_rate: int
    wall_clock_us: WallClockUs
    samples: list[ECGSampleInDTO]


@dataclass(frozen=True)
class AccelerometerSampleInDTO:
    """Single accelerometer sample from the collector transport."""

    x: float
    y: float
    z: float
    wall_clock_us: WallClockUs
    polar_clock_us: DeviceTimestampUs
    receiver_clock_us: ReceiverClockUs
    time_verified: bool


@dataclass(frozen=True)
class AccelerometerBatchInDTO:
    """Accelerometer batch from the collector transport."""

    device_id: str
    sample_rate: int
    wall_clock_us: WallClockUs
    samples: list[AccelerometerSampleInDTO]


@dataclass(frozen=True)
class DeviceStatusUpdateDTO:
    """Runtime device status update from a collector."""

    device_id: str
    status: DeviceStatus
    battery_level: int | None = None
    error_message: str | None = None
