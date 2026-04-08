"""Typed DTOs for read/query use cases."""

from dataclasses import dataclass
from typing import TypeVar

from ecg_common import DeviceStatus
from pydantic import BaseModel, ConfigDict

from ecg_aggregator.domain.devices import is_simulated_collector, is_simulated_device
from ecg_aggregator.domain.time import (
    DeviceTimestampUs,
    GlobalTimeSeconds,
    HostTimeSeconds,
    ReceiverClockUs,
    Seconds,
    WallClockUs,
)

SampleT = TypeVar("SampleT")
ItemT = TypeVar("ItemT")


class SyncInfoDTO(BaseModel):
    """Synchronization status DTO."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    confidence: float
    drift_ppm: float
    sample_count: int


class DeviceStatusDTO(BaseModel):
    """Device runtime status DTO."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    device_id: str
    collector_id: str | None = None
    collector_name: str | None = None
    status: DeviceStatus
    last_update: HostTimeSeconds | None = None
    battery_level: int | None = None
    error_message: str | None = None

    @property
    def is_simulated(self) -> bool:
        if self.collector_id is not None:
            return is_simulated_collector(self.collector_id)
        return is_simulated_device(self.device_id)


class DeviceSummaryDTO(BaseModel):
    """Device summary DTO."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    device_id: str
    sync_ready: bool
    sync: SyncInfoDTO | None = None

    @property
    def is_simulated(self) -> bool:
        return is_simulated_device(self.device_id)

    @property
    def sync_confidence(self) -> float:
        return self.sync.confidence if self.sync else -1.0

    @property
    def sync_sample_count(self) -> int:
        return self.sync.sample_count if self.sync else -1


class DeviceInfoDTO(BaseModel):
    """Complete device information DTO."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    device_id: str
    first_seen: HostTimeSeconds | None = None
    last_seen: HostTimeSeconds | None = None
    total_samples: int = 0
    nickname: str | None = None
    sync_ready: bool = False
    sync: SyncInfoDTO | None = None
    collector_id: str | None = None
    status: DeviceStatus = DeviceStatus.DISCONNECTED
    last_update: HostTimeSeconds | None = None
    battery_level: int | None = None
    error_message: str | None = None

    @property
    def is_simulated(self) -> bool:
        if self.collector_id is not None:
            return is_simulated_collector(self.collector_id)
        return is_simulated_device(self.device_id)

    @property
    def sync_confidence(self) -> float:
        return self.sync.confidence if self.sync else -1.0

    @property
    def sync_sample_count(self) -> int:
        return self.sync.sample_count if self.sync else -1

    @property
    def has_nickname(self) -> bool:
        return self.nickname is not None and self.nickname.strip() != ""

    @property
    def normalized_nickname(self) -> str:
        return self.nickname.lower() if self.nickname else ""


class SessionInfoDTO(BaseModel):
    """Session information DTO."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: int
    start_time: GlobalTimeSeconds
    end_time: GlobalTimeSeconds | None
    device_count: int
    sample_count: int
    notes: str | None
    duration_seconds: Seconds | None
    ecg_sample_count: int
    acc_sample_count: int
    devices: list[str]


class ECGSessionSampleDTO(BaseModel):
    """ECG session sample DTO."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: int
    global_time: GlobalTimeSeconds
    raw_value: int
    confidence: float
    wall_clock_us: WallClockUs
    receiver_clock_us: ReceiverClockUs
    polar_clock_us: DeviceTimestampUs
    time_verified: bool


class AccelerometerSessionSampleDTO(BaseModel):
    """Accelerometer session sample DTO."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: int
    global_time: GlobalTimeSeconds
    x: float
    y: float
    z: float
    magnitude: float
    confidence: float
    wall_clock_us: WallClockUs
    receiver_clock_us: ReceiverClockUs
    polar_clock_us: DeviceTimestampUs
    time_verified: bool


@dataclass(frozen=True)
class PaginatedResult[ItemT]:
    """Paginated result set."""

    items: list[ItemT]
    total: int
    limit: int | None
    offset: int


@dataclass(frozen=True)
class GroupedSamplesResult[SampleT]:
    """Grouped sample result set."""

    session_id: int
    devices: dict[str, list[SampleT]]
    count: int
