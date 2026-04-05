"""System-level HTTP routes."""

from typing import Annotated

from ecg_common import __version__
from fastapi import APIRouter, Depends

from ecg_aggregator.api.deps import get_runtime
from ecg_aggregator.api.models import (
    RootEndpoints,
    RootResponse,
    StatsResponse,
    VersionResponse,
)
from ecg_aggregator.application.runtime import ApplicationRuntime
from ecg_aggregator.domain.realtime import BufferStatsSnapshot

router = APIRouter(tags=["system"])


@router.get("/", response_model=RootResponse)
async def root() -> RootResponse:
    """Root endpoint."""
    return RootResponse(
        service="ECG Streaming API",
        version=__version__,
        endpoints=RootEndpoints(
            websocket_ecg="/ws/ecg",
            websocket_accelerometer="/ws/accelerometer",
            devices="/devices",
            devices_all="/devices/all",
            devices_status="/devices/status",
            device_nickname="/devices/{device_id}/nickname",
            collectors="/collectors",
            stats="/stats",
            ecg_buffer="/buffer/stats",
            ecg_latest="/buffer/latest",
            accelerometer_buffer="/accelerometer/buffer/stats",
            accelerometer_latest="/accelerometer/buffer/latest",
            session_start="/sessions/start",
            session_stop="/sessions/stop",
            session_active="/sessions/active",
            sessions="/sessions",
        ),
    )


@router.get("/version", response_model=VersionResponse)
async def get_version() -> VersionResponse:
    """Get API version information."""
    return VersionResponse(version=__version__)


@router.get("/stats", response_model=StatsResponse)
async def get_stats(
    runtime: Annotated[ApplicationRuntime, Depends(get_runtime)],
) -> StatsResponse:
    """Get synchronization statistics."""
    stats = runtime.system_query_service.get_stats()
    return StatsResponse(
        sync=stats.sync,
        grpc=stats.ingest,
        ecg_websocket_connections=stats.ecg_websocket_connections,
        acc_websocket_connections=stats.acc_websocket_connections,
        ecg_buffer=BufferStatsSnapshot.model_validate(stats.ecg_buffer.model_dump()),
        acc_buffer=BufferStatsSnapshot.model_validate(stats.acc_buffer.model_dump()),
    )
