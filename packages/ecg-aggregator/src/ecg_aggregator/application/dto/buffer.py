"""Typed DTOs for buffer queries."""

from pydantic import BaseModel, ConfigDict

from ecg_aggregator.domain.time import (
    DeviceTimestampUs,
    GlobalTimeSeconds,
    ReceiverClockUs,
    WallClockUs,
)


class BufferedECGSampleDTO(BaseModel):
    """Latest ECG sample DTO."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    device_id: str
    global_time: GlobalTimeSeconds
    confidence: float
    wall_clock_us: WallClockUs
    receiver_clock_us: ReceiverClockUs
    polar_clock_us: DeviceTimestampUs
    time_verified: bool
    raw_value: int


class BufferedAccelerometerSampleDTO(BaseModel):
    """Latest accelerometer sample DTO."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    device_id: str
    global_time: GlobalTimeSeconds
    confidence: float
    wall_clock_us: WallClockUs
    receiver_clock_us: ReceiverClockUs
    polar_clock_us: DeviceTimestampUs
    time_verified: bool
    x: float
    y: float
    z: float
    magnitude: float
