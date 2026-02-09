"""System-level API models."""

from pydantic import BaseModel, ConfigDict


class RootEndpoints(BaseModel):
    """API endpoint map."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    websocket_ecg: str
    websocket_accelerometer: str
    devices: str
    devices_all: str
    devices_status: str
    device_nickname: str
    collectors: str
    stats: str
    ecg_buffer: str
    ecg_latest: str
    accelerometer_buffer: str
    accelerometer_latest: str
    session_start: str
    session_stop: str
    session_active: str
    sessions: str


class RootResponse(BaseModel):
    """Root endpoint response."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    service: str
    version: str
    endpoints: RootEndpoints


class VersionResponse(BaseModel):
    """Version response."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: str


class DebugConnectionInfo(BaseModel):
    """Debug connection info."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: int
    client: tuple[str, int] | None
    headers: dict[str, str]


class DebugConnectionsResponse(BaseModel):
    """Response model for debug connections."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ecg_count: int
    acc_count: int
    ecg_connections: list[DebugConnectionInfo]
    acc_connections: list[DebugConnectionInfo]
