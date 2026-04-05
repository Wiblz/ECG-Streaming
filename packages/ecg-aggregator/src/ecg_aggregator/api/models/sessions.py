"""Session-related API models."""

from pydantic import BaseModel, ConfigDict

from ecg_aggregator.application.dto.query import (
    AccelerometerSessionSampleDTO,
    ECGSessionSampleDTO,
)
from ecg_aggregator.domain.time import GlobalTimeSeconds, Seconds


class SessionInfo(BaseModel):
    """Session information response model."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: int
    start_time: GlobalTimeSeconds
    end_time: GlobalTimeSeconds | None
    device_count: int
    sample_count: int
    notes: str | None
    duration_seconds: Seconds | None
    ecg_sample_count: int
    acc_sample_count: int
    devices: list[str]


class SessionsResponse(BaseModel):
    """Response model for /sessions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sessions: list[SessionInfo]
    count: int
    total: int
    limit: int | None = None
    offset: int = 0


class ActiveSessionResponse(BaseModel):
    """Response model for /sessions/active."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    active: bool
    session_id: int | None
    session: SessionInfo | None = None
    error: str | None = None


class SessionActionResponse(BaseModel):
    """Response model for session start/stop."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    success: bool
    session_id: int
    message: str


class SessionSamplesResponse(BaseModel):
    """Response model for ECG session samples."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    session_id: int
    devices: dict[str, list[ECGSessionSampleDTO]]
    count: int


class SessionAccelerometerSamplesResponse(BaseModel):
    """Response model for accelerometer session samples."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    session_id: int
    devices: dict[str, list[AccelerometerSessionSampleDTO]]
    count: int


class DeleteSessionResponse(BaseModel):
    """Response model for session deletion."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    success: bool
    message: str | None = None
    error: str | None = None


class ImportSessionResponse(BaseModel):
    """Response model for session import."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    success: bool
    session_id: int
    message: str
