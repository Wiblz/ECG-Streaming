"""Calibration WebSocket routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, WebSocket

from ecg_aggregator.api.deps import get_calibration_hub
from ecg_aggregator.infrastructure.realtime.calibration_hub import CalibrationWebSocketHub

router = APIRouter(tags=["calibration"])


@router.websocket("/ws/calibration")
async def websocket_calibration(
    websocket: WebSocket,
    calibration_hub: Annotated[CalibrationWebSocketHub, Depends(get_calibration_hub)],
) -> None:
    """WebSocket endpoint for calibration session management."""
    await calibration_hub.handle_websocket(websocket)
