"""Typed delivery DTOs for realtime status channels."""

from typing import Literal

from ecg_common import DeviceStatus
from pydantic import BaseModel, ConfigDict

from ecg_aggregator.domain.realtime import BufferStatsSnapshot
from ecg_aggregator.domain.time import HostTimeSeconds

SSEEventType = Literal[
    "connected", "collector_update", "device_update", "buffer_stats", "heartbeat"
]

CollectorStatus = Literal["CONNECTED", "HEALTHY", "DISCONNECTED"]


class ConnectedEventData(BaseModel):
    """Data for the initial SSE connected event."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    timestamp: HostTimeSeconds


class CollectorUpdateData(BaseModel):
    """Payload for collector status updates."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    collector_id: str
    display_name: str | None = None
    status: CollectorStatus | None = None
    device_count: int | None = None
    samples_sent: int | None = None
    active_devices: int | None = None


class DeviceUpdateData(BaseModel):
    """Payload for device runtime updates."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    device_id: str
    collector_id: str
    status: DeviceStatus
    battery_level: int | None = None


class BufferStatsData(BaseModel):
    """Payload for periodic buffer statistics."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ecg_buffer: BufferStatsSnapshot
    acc_buffer: BufferStatsSnapshot


class HeartbeatEventData(BaseModel):
    """Heartbeat payload for SSE keepalive."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    timestamp: HostTimeSeconds


SSEEventData = (
    ConnectedEventData
    | CollectorUpdateData
    | DeviceUpdateData
    | BufferStatsData
    | HeartbeatEventData
)
