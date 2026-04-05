"""Typed DTOs for system/debug queries."""

from typing import TypedDict

from pydantic import BaseModel, ConfigDict

from ecg_aggregator.domain.realtime import BufferStatsSnapshot
from ecg_aggregator.sync.types import SyncStats


class IngestStats(TypedDict):
    """Structured ingest-side runtime statistics."""

    collectors_connected: int
    collectors: list[str]
    samples_received: int
    acc_samples_received: int
    active_session_id: int | None


class DebugConnectionDTO(BaseModel):
    """Debug information for one active websocket connection."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: int
    client: tuple[str, int] | None
    headers: dict[str, str]


class SystemStatsDTO(BaseModel):
    """Aggregate system stats for API consumers."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sync: SyncStats
    ingest: IngestStats
    ecg_websocket_connections: int
    acc_websocket_connections: int
    ecg_buffer: BufferStatsSnapshot
    acc_buffer: BufferStatsSnapshot


class DebugConnectionsDTO(BaseModel):
    """Detailed debug information for active websocket connections."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ecg_count: int
    acc_count: int
    ecg_connections: list[DebugConnectionDTO]
    acc_connections: list[DebugConnectionDTO]
