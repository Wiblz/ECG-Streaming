"""Unified gRPC client for streaming CollectorMessages to aggregator.

Used by both BLE and USB collectors to forward data to the aggregator.
"""

import asyncio
import contextlib
import time
from collections.abc import AsyncIterator

import grpc
from ecg_common.logging import get_logger
from ecg_common.proto import collector_aggregator_pb2, collector_aggregator_pb2_grpc

logger = get_logger(__name__)

CONNECT_TIMEOUT_S = 5.0
INITIAL_BACKOFF_S = 1.0
MAX_BACKOFF_S = 30.0
HEALTHY_STREAM_S = 30.0
REJECTED_BACKOFF_S = 60.0
# ~50s of frames at 20 devices (~10 batch messages/s per device)
MAX_QUEUE_SIZE = 10_000
DROP_LOG_INTERVAL_S = 5.0


class CollectorGrpcClient:
    """gRPC client for streaming CollectorMessages to aggregator.

    This client is used by both BLE and USB collectors to forward data.
    It owns reconnection: `run()` supervises connect/stream cycles with
    exponential backoff and re-registers on every new stream.
    """

    def __init__(
        self,
        collector_id: str,
        aggregator_host: str,
        aggregator_port: int,
        device_ids: list[str] | None = None,
        display_name: str = "",
        metadata: dict[str, str] | None = None,
        device_nicknames: dict[str, str] | None = None,
    ) -> None:
        """Initialize collector gRPC client.

        Args:
            collector_id: Unique identifier for this collector
            aggregator_host: Aggregator server hostname/IP
            aggregator_port: Aggregator server port
            device_ids: List of device IDs (can be empty, updated later)
            display_name: Human-readable name
            metadata: Optional metadata dict
            device_nicknames: Optional device ID -> nickname mapping from config
        """
        self.collector_id = collector_id
        self.aggregator_host = aggregator_host
        self.aggregator_port = aggregator_port
        self.device_ids = device_ids or []
        self.display_name = display_name or collector_id
        self.metadata = metadata or {}
        self.device_nicknames = device_nicknames or {}

        self._channel: grpc.aio.Channel | None = None
        self._stub: collector_aggregator_pb2_grpc.ECGStreamingServiceStub | None = None
        self._message_queue: asyncio.Queue[collector_aggregator_pb2.CollectorMessage] = (
            asyncio.Queue(maxsize=MAX_QUEUE_SIZE)
        )
        self._running = False
        self._connected = False
        self._registration_rejected = False
        self._dropped_messages = 0
        self._last_drop_log_ts = 0.0

    async def connect(self) -> bool:
        """Connect to aggregator.

        Returns:
            True if connected successfully
        """
        try:
            target = f"{self.aggregator_host}:{self.aggregator_port}"
            self._channel = grpc.aio.insecure_channel(target)
            await asyncio.wait_for(self._channel.channel_ready(), timeout=CONNECT_TIMEOUT_S)

            self._stub = collector_aggregator_pb2_grpc.ECGStreamingServiceStub(self._channel)
            self._connected = True

            logger.info(f"Connected to aggregator: {target}")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to aggregator: {e!r}")
            await self._close_channel()
            return False

    async def disconnect(self) -> None:
        """Disconnect from aggregator and stop the supervised run loop."""
        self._running = False
        await self._close_channel()
        logger.info("Disconnected from aggregator")

    async def _close_channel(self) -> None:
        """Close the current channel without stopping the run loop."""
        self._connected = False
        channel = self._channel
        self._channel = None
        self._stub = None
        if channel:
            with contextlib.suppress(Exception):
                await channel.close()

    async def send_message(self, message: collector_aggregator_pb2.CollectorMessage) -> None:
        """Queue a message to send to aggregator, dropping the oldest when full.

        Args:
            message: CollectorMessage to send
        """
        try:
            self._message_queue.put_nowait(message)
        except asyncio.QueueFull:
            with contextlib.suppress(asyncio.QueueEmpty):
                self._message_queue.get_nowait()
            self._dropped_messages += 1
            self._message_queue.put_nowait(message)

            now = time.monotonic()
            if now - self._last_drop_log_ts >= DROP_LOG_INTERVAL_S:
                self._last_drop_log_ts = now
                logger.warning(
                    f"Send queue full ({MAX_QUEUE_SIZE}); dropping oldest messages "
                    f"({self._dropped_messages} dropped total)"
                )

    async def _message_generator(
        self,
    ) -> AsyncIterator[collector_aggregator_pb2.CollectorMessage]:
        """Generate messages to send to aggregator.

        Yields:
            CollectorMessages from queue
        """
        # Send registration first
        registration = collector_aggregator_pb2.CollectorRegistration(
            collector_id=self.collector_id,
            device_ids=self.device_ids,
            display_name=self.display_name,
            metadata=self.metadata,
            device_nicknames=self.device_nicknames,
        )

        reg_msg = collector_aggregator_pb2.CollectorMessage()
        reg_msg.registration.CopyFrom(registration)
        yield reg_msg

        logger.info(f"Sent registration for collector: {self.collector_id}")

        # Send queued messages
        while self._running:
            try:
                message = await self._message_queue.get()
                yield message

            except Exception as e:
                logger.error(f"Error getting message from queue: {e}")
                break

    async def _stream_loop(self) -> None:
        """Main streaming loop."""
        if not self._stub:
            logger.error("gRPC stub not initialized")
            return

        response_stream = self._stub.StreamECG(self._message_generator())
        try:
            # Process responses from aggregator
            async for response in response_stream:
                msg_type = response.WhichOneof("message")

                if msg_type == "registration_ack":
                    ack = response.registration_ack
                    if ack.accepted:
                        logger.info(
                            f"Registration accepted: {ack.message} (server time: {ack.server_time_ms})"
                        )
                    else:
                        logger.error(f"Registration rejected: {ack.message}")
                        self._registration_rejected = True
                        break

                elif msg_type == "sync_status":
                    # Could handle time sync here
                    pass

                elif msg_type == "control":
                    # Could handle control commands here
                    logger.info(f"Received control command: {response.control}")

        except grpc.RpcError as e:
            logger.error(f"gRPC stream error: {e}")

        except Exception as e:
            logger.error(f"Stream loop error: {e}", exc_info=True)
        finally:
            self._connected = False
            with contextlib.suppress(Exception):
                response_stream.cancel()

    async def run(self) -> None:
        """Run the gRPC client, reconnecting with backoff until disconnected."""
        self._running = True
        backoff_s = INITIAL_BACKOFF_S

        while self._running:
            stream_started: float | None = None
            if await self.connect():
                stream_started = time.monotonic()
                try:
                    await self._stream_loop()
                finally:
                    await self._close_channel()

            if not self._is_running():
                break

            if self._registration_rejected:
                self._registration_rejected = False
                delay = REJECTED_BACKOFF_S
                logger.error(f"Aggregator rejected registration; retrying in {delay:.0f}s")
            else:
                if (
                    stream_started is not None
                    and time.monotonic() - stream_started >= HEALTHY_STREAM_S
                ):
                    backoff_s = INITIAL_BACKOFF_S
                delay = backoff_s
                backoff_s = min(backoff_s * 2.0, MAX_BACKOFF_S)
                logger.warning(f"Reconnecting to aggregator in {delay:.1f}s")

            await asyncio.sleep(delay)

    def _is_running(self) -> bool:
        """Read the running flag, which other tasks may clear via disconnect()."""
        return self._running

    @property
    def connected(self) -> bool:
        """Check if connected to aggregator.

        Returns:
            True if connected
        """
        return self._connected

    @property
    def dropped_messages(self) -> int:
        """Count of messages dropped due to a full send queue.

        Returns:
            Total dropped message count
        """
        return self._dropped_messages
