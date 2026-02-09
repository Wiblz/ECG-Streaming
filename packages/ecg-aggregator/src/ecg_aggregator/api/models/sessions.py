"""Session-related API models."""

from pydantic import BaseModel, ConfigDict

from ecg_aggregator.api.models.base import (
    AccelerometerSessionSampleModel,
    ECGSessionSampleModel,
)


class SessionInfo(BaseModel):
    """Session information response model."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: int
    start_time: float
    end_time: float | None
    device_count: int
    sample_count: int
    notes: str | None
    duration_seconds: float | None
    ecg_sample_count: int
    acc_sample_count: int
    devices: list[str]


class SessionsResponse(BaseModel):
    """Response model for /sessions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sessions: list[SessionInfo]
    count: int


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
    devices: dict[str, list[ECGSessionSampleModel]]
    count: int


class SessionAccelerometerSamplesResponse(BaseModel):
    """Response model for accelerometer session samples."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    session_id: int
    devices: dict[str, list[AccelerometerSessionSampleModel]]
    count: int


class BackfillResponse(BaseModel):
    """Response model for session backfill."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    success: bool
    sessions_created: int
    message: str


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
