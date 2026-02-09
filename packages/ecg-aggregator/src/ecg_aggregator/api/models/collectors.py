"""Collector-related API models."""

from pydantic import BaseModel, ConfigDict, Field


class CollectorInfo(BaseModel):
    """Collector information response model."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    collector_id: str
    display_name: str | None = None
    device_ids: list[str] = Field(default_factory=list)
    version: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
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

    model_config = ConfigDict(extra="forbid", frozen=True)

    collectors: list[CollectorInfo]
    count: int
