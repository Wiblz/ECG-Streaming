"""Shared FastAPI dependencies for the API layer."""

from typing import cast

from fastapi import Request

from ecg_aggregator.application.runtime import ApplicationRuntime
from ecg_aggregator.infrastructure.realtime.calibration_hub import CalibrationWebSocketHub
from ecg_aggregator.infrastructure.realtime.realtime_ws_hub import RealtimeWebSocketHub
from ecg_aggregator.infrastructure.realtime.sse_hub import SSEHub


def get_runtime(request: Request) -> ApplicationRuntime:
    """Return the application runtime stored on the FastAPI app state."""
    return cast(ApplicationRuntime, request.app.state.runtime)


def get_sse_hub(request: Request) -> SSEHub:
    """Return the SSE hub stored on the FastAPI app state."""
    return cast(SSEHub, request.app.state.sse_hub)


def get_realtime_hub(request: Request) -> RealtimeWebSocketHub:
    """Return the realtime WebSocket hub stored on the FastAPI app state."""
    return cast(RealtimeWebSocketHub, request.app.state.realtime_hub)


def get_calibration_hub(request: Request) -> CalibrationWebSocketHub:
    """Return the calibration hub stored on the FastAPI app state."""
    return cast(CalibrationWebSocketHub, request.app.state.calibration_hub)
