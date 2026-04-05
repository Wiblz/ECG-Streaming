"""Typed DTOs for calibration control and delivery."""

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict

from ecg_aggregator.domain.time import GlobalTimeSeconds, HostTimeSeconds, OffsetSeconds
from ecg_aggregator.sync.types import CalibrationSessionStats, DeviceCalibrationStatus


class CalibrationNoActiveSessionMessage(BaseModel):
    """Notification that no calibration session is active."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["no_active_session"] = "no_active_session"
    timestamp: HostTimeSeconds


class CalibrationSessionActiveMessage(BaseModel):
    """Snapshot of the active calibration session."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["session_active"] = "session_active"
    session_id: int
    devices: dict[str, DeviceCalibrationStatus]
    stats: CalibrationSessionStats


class CalibrationErrorMessage(BaseModel):
    """Error response for invalid calibration commands."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["error"] = "error"
    message: str


class CalibrationSessionStartedMessage(BaseModel):
    """Response emitted when a calibration session starts."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["session_started"] = "session_started"
    session_id: int
    target_devices: list[str]
    start_time: HostTimeSeconds


class CalibrationSessionStoppedMessage(BaseModel):
    """Response emitted when a calibration session stops."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["session_stopped"] = "session_stopped"
    session_id: int


class CalibrationFlashRecordedMessage(BaseModel):
    """Response emitted when a flash event is recorded."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["flash_recorded"] = "flash_recorded"
    flash_id: int
    timestamp: HostTimeSeconds
    flash_count: int


class CalibrationDevicesStatusMessage(BaseModel):
    """Per-device calibration status snapshot."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["devices_status"] = "devices_status"
    devices: dict[str, DeviceCalibrationStatus]
    stats: CalibrationSessionStats


class CalibrationTapDetectedMessage(BaseModel):
    """Realtime notification for a detected tap."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["tap_detected"] = "tap_detected"
    device_id: str
    tap_timestamp: GlobalTimeSeconds
    magnitude: float
    confidence: float


class CalibrationAlignmentUpdatedMessage(BaseModel):
    """Realtime notification for an updated device alignment."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["alignment_updated"] = "alignment_updated"
    device_id: str
    status: str
    confidence: float
    offset: OffsetSeconds
    tap_count: int
    mean_error: float | None = None
    std_error: float | None = None
    ready: bool


class StartCalibrationSessionRequest(BaseModel):
    """Command to start a calibration session."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["start_session"]
    target_devices: list[str]
    name: str | None = None
    notes: str | None = None


class StopCalibrationSessionRequest(BaseModel):
    """Command to stop the active calibration session."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["stop_session"]


class CalibrationFlashEventRequest(BaseModel):
    """Command to record a calibration flash event."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["flash_event"]
    timestamp: HostTimeSeconds | None = None
    event_type: Literal["visual", "vibration"] | None = None
    pattern_id: str | None = None


class GetCalibrationStatusRequest(BaseModel):
    """Command to query the active calibration session status."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["get_status"]


CalibrationInboundMessage = (
    StartCalibrationSessionRequest
    | StopCalibrationSessionRequest
    | CalibrationFlashEventRequest
    | GetCalibrationStatusRequest
)

CalibrationOutboundMessage = (
    CalibrationNoActiveSessionMessage
    | CalibrationSessionActiveMessage
    | CalibrationErrorMessage
    | CalibrationSessionStartedMessage
    | CalibrationSessionStoppedMessage
    | CalibrationFlashRecordedMessage
    | CalibrationDevicesStatusMessage
    | CalibrationTapDetectedMessage
    | CalibrationAlignmentUpdatedMessage
)


@dataclass(frozen=True)
class CalibrationCommandResult:
    """Typed response from a calibration command."""

    response: CalibrationOutboundMessage
    broadcast: bool
