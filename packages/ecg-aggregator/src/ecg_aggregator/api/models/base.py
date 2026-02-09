"""Shared API models."""

from pydantic import BaseModel, ConfigDict

from ecg_aggregator.sync.types import SyncStats


class SyncInfo(BaseModel):
    """Time synchronization status."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    confidence: float
    drift_ppm: float
    sample_count: int


class BufferStats(BaseModel):
    """Buffer statistics payload."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    total_samples: int
    duration_seconds: float
    device_count: int
    samples_per_device: dict[str, int]
    samples_per_second: float
    samples_per_second_per_device: dict[str, float]
    oldest_timestamp: float | None
    newest_timestamp: float | None
    total_processed: int
    buffer_utilization: float


class BufferedECGSampleModel(BaseModel):
    """ECG sample response model."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    device_id: str
    global_time: float
    confidence: float
    wall_clock_us: int
    receiver_clock_us: int
    polar_clock_us: int
    time_verified: bool
    raw_value: int


class BufferedAccelerometerSampleModel(BaseModel):
    """Accelerometer sample response model."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    device_id: str
    global_time: float
    confidence: float
    wall_clock_us: int
    receiver_clock_us: int
    polar_clock_us: int
    time_verified: bool
    x: float
    y: float
    z: float
    magnitude: float


class ECGSessionSampleModel(BaseModel):
    """ECG session sample (grouped by device_id, so no device_id field)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    global_time: float
    raw_value: int
    confidence: float
    wall_clock_us: int
    receiver_clock_us: int
    polar_clock_us: int
    time_verified: bool


class AccelerometerSessionSampleModel(BaseModel):
    """Accelerometer session sample (grouped by device_id, so no device_id field)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    global_time: float
    x: float
    y: float
    z: float
    magnitude: float
    confidence: float
    wall_clock_us: int
    receiver_clock_us: int
    polar_clock_us: int
    time_verified: bool


class StatsResponse(BaseModel):
    """Response model for /stats."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sync: SyncStats
    grpc: dict[str, object]
    ecg_websocket_connections: int
    acc_websocket_connections: int
    ecg_buffer: BufferStats
    acc_buffer: BufferStats
