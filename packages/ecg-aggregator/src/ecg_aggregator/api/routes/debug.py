"""Debug HTTP routes."""

from typing import Annotated

from fastapi import APIRouter, Depends

from ecg_aggregator.api.deps import get_runtime
from ecg_aggregator.api.models import DebugConnectionInfo, DebugConnectionsResponse
from ecg_aggregator.application.runtime import ApplicationRuntime

router = APIRouter(tags=["debug"])


@router.get("/debug/connections", response_model=DebugConnectionsResponse)
@router.get("/debug/connections/", response_model=DebugConnectionsResponse)
async def debug_connections(
    runtime: Annotated[ApplicationRuntime, Depends(get_runtime)],
) -> DebugConnectionsResponse:
    """Inspect active WebSocket connections."""
    connections = runtime.system_query_service.get_debug_connections()
    return DebugConnectionsResponse(
        ecg_count=connections.ecg_count,
        acc_count=connections.acc_count,
        ecg_connections=[
            DebugConnectionInfo.model_validate(connection.model_dump())
            for connection in connections.ecg_connections
        ],
        acc_connections=[
            DebugConnectionInfo.model_validate(connection.model_dump())
            for connection in connections.acc_connections
        ],
    )
