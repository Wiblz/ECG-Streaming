"""Collector-related API models."""

from pydantic import BaseModel, ConfigDict, Field, computed_field

from ecg_aggregator.domain.devices import is_simulated_collector
from ecg_aggregator.domain.time import HostTimeSeconds


class CollectorInfo(BaseModel):
    """Collector information response model."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    collector_id: str
    display_name: str | None = None
    device_ids: list[str] = Field(default_factory=list)
    version: str | None = None
    first_seen: HostTimeSeconds | None = None
    last_seen: HostTimeSeconds | None = None
    connected_at: HostTimeSeconds | None = None
    samples_sent: int = 0
    active_devices: int = 0
    collector_type: str | None = None
    health: str  # "healthy", "warning", "disconnected"
    connected: bool

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_simulated(self) -> bool:
        return is_simulated_collector(self.collector_id)


class CollectorsResponse(BaseModel):
    """Response model for collectors list."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    collectors: list[CollectorInfo]
