"""Server-Sent Events (SSE) broadcaster for status updates."""

import asyncio
from typing import Literal, TypedDict

from ecg_common.logging import get_logger

logger = get_logger(__name__)


# SSE Event Type Literals
SSEEventType = Literal[
    "connected", "collector_update", "device_update", "buffer_stats", "heartbeat"
]

# Collector status values
CollectorStatus = Literal["CONNECTED", "HEALTHY", "DISCONNECTED"]

# Device status values
DeviceStatus = Literal["UNKNOWN", "DISCONNECTED", "CONNECTING", "CONNECTED", "STREAMING", "ERROR"]


class ConnectedEventData(TypedDict):
    """Data for connected event (sent on initial connection)."""

    timestamp: float


class CollectorUpdateData(TypedDict, total=False):
    """Data for collector_update events."""

    collector_id: str  # Required
    display_name: str
    status: CollectorStatus
    device_count: int
    samples_sent: int
    active_devices: int


class DeviceUpdateData(TypedDict, total=False):
    """Data for device_update events."""

    device_id: str  # Required
    collector_id: str  # Required
    status: DeviceStatus
    battery_level: int | None


class BufferStatsData(TypedDict):
    """Data for buffer_stats events."""

    total_samples: int
    duration_seconds: float
    device_count: int
    samples_per_device: dict[str, int]
    oldest_timestamp: float
    newest_timestamp: float
    total_processed: int
    buffer_utilization: float


class HeartbeatEventData(TypedDict):
    """Data for heartbeat event (keepalive)."""

    timestamp: float


# Union of all event data types
SSEEventData = (
    ConnectedEventData
    | CollectorUpdateData
    | DeviceUpdateData
    | BufferStatsData
    | HeartbeatEventData
)


class SSEBroadcaster:
    """Manages SSE connections and broadcasts status update events."""

    def __init__(self) -> None:
        """Initialize the SSE broadcaster."""
        self._clients: set[asyncio.Queue] = set()
        self._lock = asyncio.Lock()

    async def connect(self) -> asyncio.Queue:
        """Register a new SSE client connection.

        Returns:
            Queue for sending events to this client
        """
        client_queue: asyncio.Queue = asyncio.Queue()
        async with self._lock:
            self._clients.add(client_queue)
        logger.info(f"SSE client connected. Total clients: {len(self._clients)}")
        return client_queue

    async def disconnect(self, client_queue: asyncio.Queue) -> None:
        """Unregister an SSE client connection.

        Args:
            client_queue: The client's event queue
        """
        async with self._lock:
            self._clients.discard(client_queue)
        logger.info(f"SSE client disconnected. Total clients: {len(self._clients)}")

    async def broadcast(self, event: str, data: SSEEventData) -> None:
        """Broadcast an event to all connected SSE clients.

        Args:
            event: Event type (e.g., 'collector_update', 'device_update')
            data: Event data as dictionary (will be JSON-encoded)
        """
        if not self._clients:
            return  # No clients connected, skip broadcasting

        message = {"event": event, "data": data}

        # Create list of clients to avoid modifying set during iteration
        async with self._lock:
            clients = list(self._clients)

        # Broadcast to all clients
        for client_queue in clients:
            try:
                client_queue.put_nowait(message)
            except asyncio.QueueFull:
                logger.warning("SSE client queue full, dropping event")
            except Exception as e:
                logger.error(f"Error broadcasting to SSE client: {e}")

    def get_client_count(self) -> int:
        """Get the number of connected SSE clients.

        Returns:
            Number of active SSE connections
        """
        return len(self._clients)
