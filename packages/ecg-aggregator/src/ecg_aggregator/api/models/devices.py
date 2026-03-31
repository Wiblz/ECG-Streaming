"""Device-related API models."""

from typing import Literal

from ecg_common import DeviceStatus
from pydantic import BaseModel, ConfigDict

from ecg_aggregator.api.models.base import SyncInfo

DeviceSummarySortField = Literal["device_id", "sync_ready", "confidence", "sample_count"]
DeviceListSortField = Literal[
    "last_seen",
    "first_seen",
    "total_samples",
    "device_id",
    "nickname",
    "status",
    "last_update",
]


class DeviceNicknameUpdate(BaseModel):
    """Request model for updating device nickname."""

    nickname: str | None


class DeviceStatusInfo(BaseModel):
    """Device status information response model."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    device_id: str
    collector_id: str | None = None
    collector_name: str | None = None
    status: DeviceStatus
    last_update: float | None = None
    battery_level: int | None = None
    error_message: str | None = None


class DeviceInfo(BaseModel):
    """Complete device information response model."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    device_id: str
    first_seen: float | None = None
    last_seen: float | None = None
    total_samples: int = 0
    nickname: str | None = None
    sync_ready: bool = False
    sync: SyncInfo | None = None  # Contains confidence, drift_ppm, sample_count
    collector_id: str | None = None
    status: DeviceStatus = DeviceStatus.DISCONNECTED
    last_update: float | None = None
    battery_level: int | None = None
    error_message: str | None = None

    @property
    def sync_confidence(self) -> float:
        """Synchronization confidence with a stable fallback for sorting."""
        return self.sync.confidence if self.sync else -1.0

    @property
    def sync_sample_count(self) -> int:
        """Synchronization sample count with a stable fallback for sorting."""
        return self.sync.sample_count if self.sync else -1

    @property
    def has_nickname(self) -> bool:
        """Whether the device has a non-empty nickname."""
        return self.nickname is not None and self.nickname.strip() != ""

    @property
    def normalized_nickname(self) -> str:
        """Lowercased nickname for stable case-insensitive sorting/filtering."""
        return self.nickname.lower() if self.nickname else ""


class DeviceSummary(BaseModel):
    """Device sync summary for /devices."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    device_id: str
    sync_ready: bool
    sync: SyncInfo | None = None

    @property
    def sync_confidence(self) -> float:
        """Synchronization confidence with a stable fallback for sorting."""
        return self.sync.confidence if self.sync else -1.0

    @property
    def sync_sample_count(self) -> int:
        """Synchronization sample count with a stable fallback for sorting."""
        return self.sync.sample_count if self.sync else -1


class DevicesSummaryResponse(BaseModel):
    """Response model for /devices."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    devices: list[DeviceSummary]
    count: int
    total: int
    limit: int | None = None
    offset: int = 0


class DevicesStatusResponse(BaseModel):
    """Response model for /devices/status."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    devices: list[DeviceStatusInfo]
    count: int
    error: str | None = None


class DevicesAllResponse(BaseModel):
    """Response model for /devices/all."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    devices: list[DeviceInfo]
    count: int
    total: int
    limit: int | None = None
    offset: int = 0


class UpdateNicknameResponse(BaseModel):
    """Response model for nickname updates."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    success: bool
    device_id: str
    nickname: str | None
