"""Typed payloads for BLE collector components."""

from __future__ import annotations

from typing import NotRequired, TypedDict


class DeviceStateInfo(TypedDict):
    device_id: str
    state: str
    retry_count: int
    next_retry_seconds: NotRequired[float]


class DeviceStateStats(TypedDict):
    total_devices: int
    connected: int
    streaming: int
    failed: int
    disconnected: int
    devices: list[DeviceStateInfo]


class AdapterStats(TypedDict):
    device_count: int
    capacity: int
    utilization: float
    devices: list[str]


class BleDeviceInfo(TypedDict):
    device_id: str
    address: str | None
    adapter: str | None
    status: int
    connected: bool
    battery_level: NotRequired[int]
