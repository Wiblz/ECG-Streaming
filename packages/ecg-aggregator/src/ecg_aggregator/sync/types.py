"""Typed payloads for sync and calibration stats."""

from typing import NotRequired, TypedDict

from ecg_aggregator.domain.time import (
    GlobalTimeSeconds,
    HostTimeSeconds,
    OffsetSeconds,
    Seconds,
)


class DeviceSpikeStats(TypedDict):
    buffer_size: int
    last_tap: GlobalTimeSeconds


class SpikeDetectorStats(TypedDict):
    total_taps_detected: int
    active_devices: int
    devices: dict[str, DeviceSpikeStats]


class DeviceSyncStats(TypedDict):
    ready: bool
    dropouts: int
    drift: NotRequired[Seconds]
    drift_ppm: NotRequired[float]
    offset: NotRequired[OffsetSeconds]
    confidence: NotRequired[float]
    sample_count: NotRequired[int]
    age_seconds: NotRequired[Seconds]


class SyncStats(TypedDict):
    total_devices: int
    ready_devices: int
    devices: dict[str, DeviceSyncStats]


class DeviceCalibrationStatus(TypedDict):
    device_id: str
    status: str
    confidence: float
    tap_count: int
    ready: bool
    offset: NotRequired[OffsetSeconds]
    mean_error: NotRequired[Seconds | None]
    std_error: NotRequired[Seconds | None]


class CalibrationSessionStats(TypedDict):
    session_id: int
    start_time: HostTimeSeconds
    duration: Seconds
    target_devices: int
    flash_count: int
    total_taps: int
    aligned_devices: int
    ready_devices: int
