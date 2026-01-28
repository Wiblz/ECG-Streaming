"""Pydantic models for API requests and responses."""

from typing import Any

from pydantic import BaseModel


class DeviceNicknameUpdate(BaseModel):
    """Request model for updating device nickname."""

    nickname: str | None


class CollectorInfo(BaseModel):
    """Collector information response model."""

    collector_id: str
    display_name: str | None = None
    device_ids: list[str] = []
    version: str | None = None
    metadata: dict[str, Any] = {}
    first_seen: float | None = None
    last_seen: float | None = None
    connected_at: float | None = None
    last_heartbeat: float | None = None
    time_since_heartbeat: float | None = None
    samples_sent: int = 0
    active_devices: int = 0
    health: str  # "healthy", "warning", "disconnected"
    connected: bool


class CollectorsResponse(BaseModel):
    """Response model for collectors list."""

    collectors: list[CollectorInfo]
    count: int


class DeviceStatusInfo(BaseModel):
    """Device status information response model."""

    device_id: str
    collector_id: str | None = None
    collector_name: str | None = None
    status: str  # "UNKNOWN", "DISCONNECTED", "CONNECTING", "CONNECTED", "STREAMING", "ERROR"
    last_update: float | None = None
    battery_level: int | None = None
    error_message: str | None = None


class DeviceInfo(BaseModel):
    """Complete device information response model."""

    device_id: str
    first_seen: float | None = None
    last_seen: float | None = None
    total_samples: int = 0
    nickname: str | None = None
    sync_ready: bool = False
    sync: dict[str, Any] | None = None  # Contains confidence, drift_ppm, sample_count
    collector_id: str | None = None
    status: str = "DISCONNECTED"
    last_update: float | None = None
    battery_level: int | None = None
    error_message: str | None = None
