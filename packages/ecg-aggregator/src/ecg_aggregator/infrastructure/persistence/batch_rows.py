"""Typed row definitions for sample batch inserts."""

from typing import NamedTuple


class ECGBatchRow(NamedTuple):
    device_id: str
    global_time: float
    device_timestamp: float
    raw_value: int
    confidence: float
    session_id: int | None
    wall_clock_us: int | None
    receiver_clock_us: int | None
    time_verified: bool


class AccBatchRow(NamedTuple):
    device_id: str
    global_time: float
    device_timestamp: float
    x: float
    y: float
    z: float
    confidence: float
    session_id: int | None
    wall_clock_us: int | None
    receiver_clock_us: int | None
    time_verified: bool
