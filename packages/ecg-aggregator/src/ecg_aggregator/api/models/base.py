"""Shared API models."""

from pydantic import BaseModel, ConfigDict

from ecg_aggregator.application.dto.system import IngestStats
from ecg_aggregator.domain.realtime import BufferStatsSnapshot
from ecg_aggregator.sync.types import SyncStats


class SyncInfo(BaseModel):
    """Time synchronization status."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    confidence: float
    drift_ppm: float
    sample_count: int


class StatsResponse(BaseModel):
    """Response model for /stats."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sync: SyncStats
    grpc: IngestStats
    ecg_websocket_connections: int
    acc_websocket_connections: int
    ecg_buffer: BufferStatsSnapshot
    acc_buffer: BufferStatsSnapshot
