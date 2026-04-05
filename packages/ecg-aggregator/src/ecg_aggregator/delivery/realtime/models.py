"""Transport models for realtime websocket delivery."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from ecg_aggregator.domain.time import (
    DeviceTimestampUs,
    GlobalTimeSeconds,
    HostTimeSeconds,
    ReceiverClockUs,
    WallClockUs,
)


class InitMessage(BaseModel):
    """Initial websocket payload listing available devices."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["init"] = "init"
    devices: list[str]
    timestamp: HostTimeSeconds


class RealtimeECGSampleModel(BaseModel):
    """Realtime ECG sample for websocket payloads."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    global_time: GlobalTimeSeconds
    confidence: float
    wall_clock_us: WallClockUs
    receiver_clock_us: ReceiverClockUs
    polar_clock_us: DeviceTimestampUs
    time_verified: bool
    raw_value: int


class RealtimeAccelerometerSampleModel(BaseModel):
    """Realtime accelerometer sample for websocket payloads."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
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
