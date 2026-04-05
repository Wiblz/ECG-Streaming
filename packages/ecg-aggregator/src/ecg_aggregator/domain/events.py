"""Domain events emitted by the aggregator core."""

import time
from dataclasses import dataclass, field

from ecg_common import DeviceStatus

from ecg_aggregator.domain.realtime import BufferStatsSnapshot
from ecg_aggregator.domain.time import GlobalTimeSeconds, HostTimeSeconds, OffsetSeconds, Seconds


@dataclass(frozen=True, slots=True)
class DomainEvent:
    """Base class for typed domain events."""

    emitted_at: HostTimeSeconds = field(default_factory=lambda: HostTimeSeconds(time.time()))


@dataclass(frozen=True, slots=True)
class CollectorRegistered(DomainEvent):
    """A collector registered with the aggregator."""

    collector_id: str = ""
    display_name: str = ""
    device_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CollectorUpdated(DomainEvent):
    """A collector runtime update was observed."""

    collector_id: str = ""
    display_name: str = ""
    active_devices: int = 0
    last_heartbeat: HostTimeSeconds = HostTimeSeconds(0.0)


@dataclass(frozen=True, slots=True)
class CollectorDisconnected(DomainEvent):
    """A collector disconnected from the aggregator."""

    collector_id: str = ""


@dataclass(frozen=True, slots=True)
class DeviceUpdated(DomainEvent):
    """A device runtime status changed."""

    device_id: str = ""
    collector_id: str | None = None
    status: DeviceStatus = DeviceStatus.UNKNOWN
    battery_level: int | None = None
    error_message: str | None = None


@dataclass(frozen=True, slots=True)
class SessionStarted(DomainEvent):
    """A recording session started."""

    session_id: int = 0
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class SessionStopped(DomainEvent):
    """A recording session stopped."""

    session_id: int = 0


@dataclass(frozen=True, slots=True)
class TapDetected(DomainEvent):
    """A calibration tap was detected."""

    device_id: str = ""
    tap_timestamp: GlobalTimeSeconds = GlobalTimeSeconds(0.0)
    magnitude: float = 0.0
    confidence: float = 0.0


@dataclass(frozen=True, slots=True)
class AlignmentUpdated(DomainEvent):
    """A device alignment estimate was updated."""

    device_id: str = ""
    status: str = ""
    confidence: float = 0.0
    offset: OffsetSeconds = OffsetSeconds(0.0)
    tap_count: int = 0
    mean_error: float | None = None
    std_error: float | None = None


@dataclass(frozen=True, slots=True)
class BufferStatsUpdated(DomainEvent):
    """Realtime buffer statistics changed."""

    ecg_stats: BufferStatsSnapshot = field(
        default_factory=lambda: BufferStatsSnapshot(
            total_samples=0,
            duration_seconds=Seconds(0.0),
            device_count=0,
            samples_per_device={},
            samples_per_second=Seconds(0.0),
            samples_per_second_per_device={},
            oldest_timestamp=None,
            newest_timestamp=None,
            total_processed=0,
            buffer_utilization=0.0,
        )
    )
    acc_stats: BufferStatsSnapshot = field(
        default_factory=lambda: BufferStatsSnapshot(
            total_samples=0,
            duration_seconds=Seconds(0.0),
            device_count=0,
            samples_per_device={},
            samples_per_second=Seconds(0.0),
            samples_per_second_per_device={},
            oldest_timestamp=None,
            newest_timestamp=None,
            total_processed=0,
            buffer_utilization=0.0,
        )
    )
    active_device_count: int | None = None
