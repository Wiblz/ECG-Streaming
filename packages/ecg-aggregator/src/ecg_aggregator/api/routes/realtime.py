"""Realtime WebSocket routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, WebSocket

from ecg_aggregator.api.deps import get_realtime_hub
from ecg_aggregator.infrastructure.realtime.realtime_ws_hub import RealtimeWebSocketHub

router = APIRouter(tags=["realtime"])


@router.websocket("/ws/ecg")
async def websocket_ecg(
    websocket: WebSocket,
    gateway: Annotated[RealtimeWebSocketHub, Depends(get_realtime_hub)],
) -> None:
    """WebSocket endpoint for real-time ECG streaming."""
    await gateway.handle_ecg_websocket(websocket)


@router.websocket("/ws/accelerometer")
async def websocket_acc(
    websocket: WebSocket,
    gateway: Annotated[RealtimeWebSocketHub, Depends(get_realtime_hub)],
) -> None:
    """WebSocket endpoint for real-time accelerometer streaming."""
    await gateway.handle_acc_websocket(websocket)
