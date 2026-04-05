"""Typed realtime payloads shared across layers."""

from pydantic import BaseModel, ConfigDict

from ecg_aggregator.domain.time import GlobalTimeSeconds, Seconds


class BufferStatsSnapshot(BaseModel):
    """Typed snapshot of a realtime buffer state."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    total_samples: int
    duration_seconds: Seconds
    device_count: int
    samples_per_device: dict[str, int]
    samples_per_second: Seconds
    samples_per_second_per_device: dict[str, Seconds]
    oldest_timestamp: GlobalTimeSeconds | None
    newest_timestamp: GlobalTimeSeconds | None
    total_processed: int
    buffer_utilization: float
