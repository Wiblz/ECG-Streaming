"""Typed DTOs for collector queries."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ecg_aggregator.domain.time import HostTimeSeconds, Seconds

CollectorHealth = Literal["healthy", "warning", "disconnected"]


class CollectorInfoDTO(BaseModel):
    """Collector information returned by collector queries."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    collector_id: str
    display_name: str | None = None
    device_ids: list[str] = Field(default_factory=list)
    version: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
    first_seen: HostTimeSeconds | None = None
    last_seen: HostTimeSeconds | None = None
    connected_at: HostTimeSeconds | None = None
    last_heartbeat: HostTimeSeconds | None = None
    time_since_heartbeat: Seconds | None = None
    samples_sent: int = 0
    active_devices: int = 0
    health: CollectorHealth
    connected: bool
