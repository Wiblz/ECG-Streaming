"""WebSocket payload models."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from ecg_aggregator.sync.types import CalibrationSessionStats, DeviceCalibrationStatus


class InitMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["init"] = "init"
    devices: list[str]
    timestamp: float


class NoActiveSessionMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["no_active_session"] = "no_active_session"
    timestamp: float


class SessionActiveMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["session_active"] = "session_active"
    session_id: int
    devices: dict[str, DeviceCalibrationStatus]
    stats: CalibrationSessionStats


class ErrorMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["error"] = "error"
    message: str


class SessionStartedMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["session_started"] = "session_started"
    session_id: int
    target_devices: list[str]
    start_time: float


class SessionStoppedMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["session_stopped"] = "session_stopped"
    session_id: int


class FlashRecordedMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["flash_recorded"] = "flash_recorded"
    flash_id: int
    timestamp: float
    flash_count: int


class DevicesStatusMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["devices_status"] = "devices_status"
    devices: dict[str, DeviceCalibrationStatus]
    stats: CalibrationSessionStats


class StartSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["start_session"]
    target_devices: list[str]
    name: str | None = None
    notes: str | None = None


class StopSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["stop_session"]


class FlashEventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["flash_event"]
    timestamp: float | None = None
    event_type: Literal["visual", "vibration"] | None = None
    pattern_id: str | None = None


class GetStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["get_status"]


OutboundMessage = (
    InitMessage
    | NoActiveSessionMessage
    | SessionActiveMessage
    | ErrorMessage
    | SessionStartedMessage
    | SessionStoppedMessage
    | FlashRecordedMessage
    | DevicesStatusMessage
)

InboundMessage = StartSessionRequest | StopSessionRequest | FlashEventRequest | GetStatusRequest
