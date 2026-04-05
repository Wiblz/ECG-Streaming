"""Server-Sent Events (SSE) broadcaster for status updates."""

import asyncio
import contextlib

from ecg_common.logging import get_logger

from ecg_aggregator.application.dto.realtime import (
    BufferStatsData,
    CollectorUpdateData,
    DeviceUpdateData,
    SSEEventData,
    SSEEventType,
)
from ecg_aggregator.application.ports.event_bus import DomainEventBus
from ecg_aggregator.domain.events import (
    BufferStatsUpdated,
    CollectorDisconnected,
    CollectorRegistered,
    CollectorUpdated,
    DeviceUpdated,
    DomainEvent,
)

logger = get_logger(__name__)


class SSEHub:
    """Manage SSE connections and broadcast status update events."""

    def __init__(self, event_bus: DomainEventBus | None = None) -> None:
        self._clients: set[asyncio.Queue] = set()
        self._lock = asyncio.Lock()
        self._event_bus = event_bus
        self._task: asyncio.Task[None] | None = None

    async def connect(self) -> asyncio.Queue:
        """Register a new SSE client connection."""
        client_queue: asyncio.Queue = asyncio.Queue()
        async with self._lock:
            self._clients.add(client_queue)
        logger.info(f"SSE client connected. Total clients: {len(self._clients)}")
        return client_queue

    async def disconnect(self, client_queue: asyncio.Queue) -> None:
        """Unregister an SSE client connection."""
        async with self._lock:
            self._clients.discard(client_queue)
        logger.info(f"SSE client disconnected. Total clients: {len(self._clients)}")

    async def broadcast(self, event: SSEEventType, data: SSEEventData) -> None:
        """Broadcast an event to all connected SSE clients."""
        if not self._clients:
            return

        message = {"event": event, "data": data.model_dump()}

        async with self._lock:
            clients = list(self._clients)

        for client_queue in clients:
            try:
                client_queue.put_nowait(message)
            except asyncio.QueueFull:
                logger.warning("SSE client queue full, dropping event")
            except Exception as e:
                logger.error(f"Error broadcasting to SSE client: {e}")

    def get_client_count(self) -> int:
        """Get the number of connected SSE clients."""
        return len(self._clients)

    async def start(self) -> None:
        """Subscribe to application events and start forwarding to SSE clients."""
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
        queue = await self._event_bus.subscribe(
            (
                CollectorRegistered,
                CollectorUpdated,
                CollectorDisconnected,
                DeviceUpdated,
                BufferStatsUpdated,
            )
        )
        try:
            while True:
                event = await queue.get()
                await self._dispatch(event)
        except asyncio.CancelledError:
            raise
        finally:
            await self._event_bus.unsubscribe(queue)

    async def _dispatch(self, event: DomainEvent) -> None:
        if isinstance(event, CollectorRegistered):
            await self.broadcast(
                "collector_update",
                CollectorUpdateData(
                    collector_id=event.collector_id,
                    display_name=event.display_name,
                    status="CONNECTED",
                    active_devices=0,
                    device_count=len(event.device_ids),
                ),
            )
        elif isinstance(event, CollectorUpdated):
            await self.broadcast(
                "collector_update",
                CollectorUpdateData(
                    collector_id=event.collector_id,
                    display_name=event.display_name,
                    status="HEALTHY",
                    active_devices=event.active_devices,
                ),
            )
        elif isinstance(event, CollectorDisconnected):
            await self.broadcast(
                "collector_update",
                CollectorUpdateData(
                    collector_id=event.collector_id,
                    status="DISCONNECTED",
                ),
            )
        elif isinstance(event, DeviceUpdated):
            if event.collector_id is None:
                return
            await self.broadcast(
                "device_update",
                DeviceUpdateData(
                    device_id=event.device_id,
                    collector_id=event.collector_id,
                    status=event.status,
                    battery_level=event.battery_level,
                ),
            )
        elif isinstance(event, BufferStatsUpdated):
            await self.broadcast(
                "buffer_stats",
                BufferStatsData(
                    ecg_buffer=event.ecg_stats,
                    acc_buffer=event.acc_stats,
                ),
            )
