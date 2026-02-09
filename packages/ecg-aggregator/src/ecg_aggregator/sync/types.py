"""Typed payloads for sync and calibration stats."""

from __future__ import annotations

from typing import NotRequired, TypedDict


class DeviceSpikeStats(TypedDict):
    buffer_size: int
    last_tap: float


class SpikeDetectorStats(TypedDict):
    total_taps_detected: int
    active_devices: int
    devices: dict[str, DeviceSpikeStats]


class DeviceSyncStats(TypedDict):
    ready: bool
    dropouts: int
    drift: NotRequired[float]
    drift_ppm: NotRequired[float]
    offset: NotRequired[float]
    confidence: NotRequired[float]
    sample_count: NotRequired[int]
    age_seconds: NotRequired[float]


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
    offset: NotRequired[float]
    mean_error: NotRequired[float | None]
    std_error: NotRequired[float | None]


class CalibrationSessionStats(TypedDict):
    session_id: int
    start_time: float
    duration: float
    target_devices: int
    flash_count: int
    total_taps: int
    aligned_devices: int
    ready_devices: int
