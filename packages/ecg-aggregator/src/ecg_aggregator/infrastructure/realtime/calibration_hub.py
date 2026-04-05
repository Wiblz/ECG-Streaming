"""Calibration websocket connection management."""

import asyncio
import contextlib
import json

from ecg_common.logging import get_logger
from fastapi import WebSocket, WebSocketDisconnect

from ecg_aggregator.application.dto.calibration import (
    CalibrationAlignmentUpdatedMessage,
    CalibrationErrorMessage,
    CalibrationOutboundMessage,
    CalibrationTapDetectedMessage,
)
from ecg_aggregator.application.ports.event_bus import DomainEventBus
from ecg_aggregator.application.services.calibration_service import CalibrationService
from ecg_aggregator.domain.events import AlignmentUpdated, DomainEvent, TapDetected

logger = get_logger(__name__)


class CalibrationWebSocketHub:
    """Manage calibration websocket connections and broadcasts."""

    def __init__(
        self,
        calibration_service: CalibrationService,
        event_bus: DomainEventBus | None = None,
    ) -> None:
        self._connections: list[WebSocket] = []
        self._calibration_service = calibration_service
        self._event_bus = event_bus
        self._task: asyncio.Task[None] | None = None

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and register a calibration websocket connection."""
        await websocket.accept()
        self._connections.append(websocket)
        logger.info(
            "Calibration WebSocket connected. Active connections: %d",
            len(self._connections),
        )

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove a calibration websocket connection if present."""
        if websocket in self._connections:
            self._connections.remove(websocket)
        logger.info(
            "Calibration WebSocket closed. Active connections: %d",
            len(self._connections),
        )

    async def broadcast(
        self,
        message: CalibrationOutboundMessage,
        *,
        exclude: WebSocket | None = None,
    ) -> None:
        """Broadcast a typed calibration message to all clients."""
        if not self._connections:
            return

        payload = message.model_dump()
        disconnected: list[WebSocket] = []
        for connection in self._connections:
            if connection == exclude:
                continue
            try:
                await connection.send_json(payload)
            except Exception as exc:
                logger.error("Error broadcasting to calibration WebSocket: %s", exc)
                disconnected.append(connection)

        for connection in disconnected:
            if connection in self._connections:
                self._connections.remove(connection)

    async def handle_websocket(self, websocket: WebSocket) -> None:
        """Handle a calibration WebSocket connection lifecycle."""
        await self.connect(websocket)

        try:
            initial_message = self._calibration_service.get_initial_message()
            await websocket.send_json(initial_message.model_dump())

            while True:
                try:
                    data = await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
                    message = json.loads(data)

                    result = self._calibration_service.handle_message(message)
                    await websocket.send_json(result.response.model_dump())

                    if result.broadcast:
                        await self.broadcast(result.response, exclude=websocket)

                except TimeoutError:
                    pass
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON from calibration client: {e}")
                    await websocket.send_json(
                        CalibrationErrorMessage(message="Invalid JSON format").model_dump()
                    )

        except WebSocketDisconnect:
            logger.info("Calibration WebSocket disconnected")
        except Exception as e:
            logger.error(f"Calibration WebSocket error: {e}")
        finally:
            self.disconnect(websocket)

    async def start(self) -> None:
        """Subscribe to application events and start forwarding to calibration clients."""
        if not self._event_bus:
            return
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        """Stop forwarding events."""
        if self._task and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def _run(self) -> None:
        assert self._event_bus is not None
        queue = await self._event_bus.subscribe((TapDetected, AlignmentUpdated))
        try:
            while True:
                event = await queue.get()
                await self._dispatch(event)
        except asyncio.CancelledError:
            raise
        finally:
            await self._event_bus.unsubscribe(queue)

    async def _dispatch(self, event: DomainEvent) -> None:
        if isinstance(event, TapDetected):
            await self.broadcast(
                CalibrationTapDetectedMessage(
                    device_id=event.device_id,
                    tap_timestamp=event.tap_timestamp,
                    magnitude=event.magnitude,
                    confidence=event.confidence,
                )
            )
        elif isinstance(event, AlignmentUpdated):
            await self.broadcast(
                CalibrationAlignmentUpdatedMessage(
                    device_id=event.device_id,
                    status=event.status,
                    confidence=event.confidence,
                    offset=event.offset,
                    tap_count=event.tap_count,
                    mean_error=event.mean_error,
                    std_error=event.std_error,
                    ready=event.status == "aligned" and event.confidence >= 0.8,
                )
            )

    async def close_all(self) -> None:
        """Close and clear all registered websocket connections."""
        for connection in self._connections.copy():
            try:
                await connection.close()
            except Exception as exc:
                logger.error("Error closing calibration WebSocket: %s", exc)
        self._connections.clear()
