"""Realtime websocket and polling delivery for browser clients."""

import asyncio
import contextlib
import time

from ecg_common.logging import get_logger
from fastapi import WebSocket, WebSocketDisconnect

from ecg_aggregator.application.dto.system import DebugConnectionDTO
from ecg_aggregator.application.utils import group_samples_by_device
from ecg_aggregator.delivery.realtime import (
    InitMessage,
    RealtimeAccelerometerSampleModel,
    RealtimeECGSampleModel,
)
from ecg_aggregator.domain.time import HostTimeSeconds
from ecg_aggregator.infrastructure.realtime.buffers import (
    AccelerometerDataBuffer,
    ECGDataBuffer,
)

logger = get_logger(__name__)


class RealtimeWebSocketHub:
    """Own websocket delivery and polling-based browser fanout."""

    SEND_TIMEOUT_SECONDS: float = 3.0
    CLOSE_TIMEOUT_SECONDS: float = 1.0

    def __init__(
        self,
        ecg_buffer: ECGDataBuffer,
        acc_buffer: AccelerometerDataBuffer,
        websocket_push_rate_hz: int,
    ) -> None:
        """Initialize realtime polling and client delivery state."""
        self.ecg_buffer = ecg_buffer
        self.acc_buffer = acc_buffer
        self.websocket_push_rate_hz = websocket_push_rate_hz
        self.broadcast_interval = 1.0 / websocket_push_rate_hz

        self.ecg_connections: list[WebSocket] = []
        self.acc_connections: list[WebSocket] = []

        self._broadcast_task: asyncio.Task | None = None
        self._acc_broadcast_task: asyncio.Task | None = None

    async def handle_ecg_websocket(self, websocket: WebSocket) -> None:
        """Handle an ECG WebSocket connection."""
        await self._handle_stream_websocket(
            websocket=websocket,
            connections=self.ecg_connections,
            buffer=self.ecg_buffer,
            stream_name="ECG",
            client_log_label="client",
        )

    async def handle_acc_websocket(self, websocket: WebSocket) -> None:
        """Handle an accelerometer WebSocket connection."""
        await self._handle_stream_websocket(
            websocket=websocket,
            connections=self.acc_connections,
            buffer=self.acc_buffer,
            stream_name="Accelerometer",
            client_log_label="acc client",
        )

    async def _handle_stream_websocket(
        self,
        websocket: WebSocket,
        connections: list[WebSocket],
        buffer: ECGDataBuffer | AccelerometerDataBuffer,
        stream_name: str,
        client_log_label: str,
    ) -> None:
        """Handle a polling-backed data stream websocket connection."""
        await websocket.accept()
        connections.append(websocket)
        logger.info(f"{stream_name} WebSocket connected. Active connections: {len(connections)}")

        try:
            devices = buffer.get_device_list()
            await websocket.send_json(
                InitMessage(devices=devices, timestamp=HostTimeSeconds(time.time())).model_dump()
            )

            while True:
                try:
                    data = await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
                    logger.debug(f"Received from {client_log_label}: {data}")
                except TimeoutError:
                    pass

        except WebSocketDisconnect:
            logger.info(f"{stream_name} WebSocket disconnected")
        except Exception as exc:
            logger.error(f"{stream_name} WebSocket error: {exc}")
        finally:
            if websocket in connections:
                connections.remove(websocket)
            logger.info(f"{stream_name} WebSocket closed. Active connections: {len(connections)}")

    async def broadcast_ecg_data(self) -> None:
        """Broadcast ECG data to all connected WebSocket clients."""
        await self._broadcast_stream_data(
            connections=self.ecg_connections,
            buffer=self.ecg_buffer,
            sample_model=RealtimeECGSampleModel,
            log_prefix="ECG_BROADCAST",
        )

    async def broadcast_acc_data(self) -> None:
        """Broadcast accelerometer data to all connected WebSocket clients."""
        await self._broadcast_stream_data(
            connections=self.acc_connections,
            buffer=self.acc_buffer,
            sample_model=RealtimeAccelerometerSampleModel,
            log_prefix="ACC_BROADCAST",
        )

    async def _broadcast_stream_data(
        self,
        connections: list[WebSocket],
        buffer: ECGDataBuffer | AccelerometerDataBuffer,
        sample_model: type[RealtimeECGSampleModel] | type[RealtimeAccelerometerSampleModel],
        log_prefix: str,
    ) -> None:
        """Poll buffered samples and broadcast them to websocket clients."""
        last_broadcast_time: dict[str, float] = {}
        broadcast_count = 0

        while True:
            try:
                broadcast_start = time.time()
                await asyncio.sleep(self.broadcast_interval)

                if not connections:
                    logger.debug(f"[{log_prefix}] No WebSocket connections, skipping")
                    continue

                current_time = time.time()
                all_samples = []
                devices = buffer.get_device_list()
                logger.debug(f"[{log_prefix}] Checking {len(devices)} devices for new samples")

                for device_id in devices:
                    since = last_broadcast_time.get(device_id, current_time - 1.0)
                    samples = buffer.get_recent_samples(since=since, device_id=device_id)
                    logger.debug(
                        f"[{log_prefix}] Device {device_id}: got {len(samples)} samples since {since:.2f}"
                    )
                    if samples:
                        newest_sample_time = samples[-1]["global_time"]
                        time_diff = newest_sample_time - current_time
                        if abs(time_diff) > 1.0:
                            logger.warning(
                                f"[{log_prefix}] Sample timestamp mismatch for {device_id}: "
                                f"newest sample at {newest_sample_time:.2f}, current time {current_time:.2f}, "
                                f"diff={time_diff:.2f}s ({'future' if time_diff > 0 else 'past'})"
                            )
                        all_samples.extend(samples)
                        last_broadcast_time[device_id] = samples[-1]["global_time"]

                if not all_samples:
                    logger.debug(
                        f"[{log_prefix}] No samples to broadcast. Buffer stats: {buffer.get_stats()}"
                    )
                    continue

                devices_data = group_samples_by_device(all_samples, sample_model)
                devices_payload = {
                    device_id: [sample.model_dump() for sample in samples]
                    for device_id, samples in devices_data.items()
                }

                broadcast_count += 1
                logger.debug(
                    f"[{log_prefix}] Broadcasting {len(all_samples)} samples from {len(devices_data)} devices (broadcast #{broadcast_count})"
                )

                message = {
                    "type": "data",
                    "devices": devices_payload,
                    "timestamp": current_time,
                    "count": len(all_samples),
                }

                send_start = time.time()
                recipients = list(connections)
                await asyncio.gather(
                    *(
                        self._send_to_connection(connection, connections, message, log_prefix)
                        for connection in recipients
                    )
                )

                send_duration = (time.time() - send_start) * 1000
                broadcast_duration = (time.time() - broadcast_start) * 1000

                if send_duration > 50:
                    logger.warning(
                        f"[{log_prefix}] Slow send: {send_duration:.1f}ms to {len(recipients)} clients"
                    )
                if broadcast_duration > 50:
                    logger.warning(
                        f"[{log_prefix}] Slow broadcast cycle: {broadcast_duration:.1f}ms total"
                    )

            except Exception as exc:
                logger.error(f"[{log_prefix}] Error in broadcast loop: {exc}", exc_info=True)
                await asyncio.sleep(1.0)

    async def _send_to_connection(
        self,
        connection: WebSocket,
        connections: list[WebSocket],
        message: dict[str, object],
        log_prefix: str,
    ) -> None:
        """Send a broadcast message to one client, dropping it on timeout or error."""
        try:
            await asyncio.wait_for(connection.send_json(message), timeout=self.SEND_TIMEOUT_SECONDS)
        except TimeoutError:
            logger.error(
                f"[{log_prefix}] Send timed out after {self.SEND_TIMEOUT_SECONDS}s, "
                f"dropping slow WebSocket client"
            )
            await self._drop_connection(connection, connections)
        except Exception as exc:
            logger.error(f"[{log_prefix}] Error sending to WebSocket: {exc}")
            await self._drop_connection(connection, connections)

    async def _drop_connection(self, connection: WebSocket, connections: list[WebSocket]) -> None:
        """Unregister a connection and close it, tolerating repeated calls."""
        if connection in connections:
            connections.remove(connection)
        with contextlib.suppress(Exception):
            await asyncio.wait_for(connection.close(), timeout=self.CLOSE_TIMEOUT_SECONDS)

    async def start(self) -> None:
        """Start polling broadcast tasks."""
        if self._broadcast_task is None or self._broadcast_task.done():
            self._broadcast_task = asyncio.create_task(self.broadcast_ecg_data())
            logger.info(f"Started ECG WebSocket broadcast at {self.websocket_push_rate_hz} Hz")

        if self._acc_broadcast_task is None or self._acc_broadcast_task.done():
            self._acc_broadcast_task = asyncio.create_task(self.broadcast_acc_data())
            logger.info(
                f"Started accelerometer WebSocket broadcast at {self.websocket_push_rate_hz} Hz"
            )

    async def stop(self) -> None:
        """Stop polling broadcast tasks."""
        if self._broadcast_task and not self._broadcast_task.done():
            self._broadcast_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._broadcast_task
            logger.info("Stopped ECG WebSocket broadcast")

        if self._acc_broadcast_task and not self._acc_broadcast_task.done():
            self._acc_broadcast_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._acc_broadcast_task
            logger.info("Stopped accelerometer WebSocket broadcast")

    async def shutdown(self) -> None:
        """Stop polling tasks and close websocket connections."""
        await self.stop()

        for connection in self.ecg_connections.copy():
            try:
                await connection.close()
            except Exception as exc:
                logger.error(f"Error closing ECG WebSocket: {exc}")
        self.ecg_connections.clear()

        for connection in self.acc_connections.copy():
            try:
                await connection.close()
            except Exception as exc:
                logger.error(f"Error closing accelerometer WebSocket: {exc}")
        self.acc_connections.clear()

    def list_ecg_connections(self) -> list[DebugConnectionDTO]:
        """Return debug metadata for ECG websocket clients."""
        return [self._to_debug_connection(connection) for connection in self.ecg_connections]

    def list_acc_connections(self) -> list[DebugConnectionDTO]:
        """Return debug metadata for accelerometer websocket clients."""
        return [self._to_debug_connection(connection) for connection in self.acc_connections]

    @staticmethod
    def _to_debug_connection(connection: WebSocket) -> DebugConnectionDTO:
        """Translate a websocket connection into a typed debug DTO."""
        return DebugConnectionDTO(
            id=id(connection),
            client=getattr(connection, "client", None),
            headers=dict(connection.headers) if hasattr(connection, "headers") else {},
        )
