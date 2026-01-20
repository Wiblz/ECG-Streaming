"""Unified gRPC client for streaming CollectorMessages to aggregator.

Used by both BLE and USB collectors to forward data to the aggregator.
"""

import asyncio
import time
from collections.abc import AsyncIterator

import grpc
from ecg_common.logging import get_logger
from ecg_common.proto import ecg_streaming_pb2, ecg_streaming_pb2_grpc

logger = get_logger(__name__)


class CollectorGrpcClient:
    """gRPC client for streaming CollectorMessages to aggregator.

    This client is used by both BLE and USB collectors to forward data.
    """

    def __init__(
        self,
        collector_id: str,
        aggregator_host: str,
        aggregator_port: int,
        device_ids: list[str] | None = None,
        display_name: str = "",
        metadata: dict[str, str] | None = None,
    ) -> None:
        """Initialize collector gRPC client.

        Args:
            collector_id: Unique identifier for this collector
            aggregator_host: Aggregator server hostname/IP
            aggregator_port: Aggregator server port
            device_ids: List of device IDs (can be empty, updated later)
            display_name: Human-readable name
            metadata: Optional metadata dict
        """
        self.collector_id = collector_id
        self.aggregator_host = aggregator_host
        self.aggregator_port = aggregator_port
        self.device_ids = device_ids or []
        self.display_name = display_name or collector_id
        self.metadata = metadata or {}

        self._channel: grpc.aio.Channel | None = None
        self._stub: ecg_streaming_pb2_grpc.ECGStreamingServiceStub | None = None
        self._message_queue: asyncio.Queue[ecg_streaming_pb2.CollectorMessage] = asyncio.Queue()
        self._running = False
        self._connected = False
        self._last_heartbeat = time.time()

    async def connect(self) -> bool:
        """Connect to aggregator.

        Returns:
            True if connected successfully
        """
        try:
            target = f"{self.aggregator_host}:{self.aggregator_port}"
            self._channel = grpc.aio.insecure_channel(target)
            await self._channel.channel_ready()

            self._stub = ecg_streaming_pb2_grpc.ECGStreamingServiceStub(self._channel)
            self._connected = True

            logger.info(f"Connected to aggregator: {target}")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to aggregator: {e}")
            self._connected = False
            return False

    async def disconnect(self) -> None:
        """Disconnect from aggregator."""
        self._running = False
        self._connected = False

        if self._channel:
            await self._channel.close()
            self._channel = None
            self._stub = None

        logger.info("Disconnected from aggregator")

    async def send_message(self, message: ecg_streaming_pb2.CollectorMessage) -> None:
        """Queue a message to send to aggregator.

        Args:
            message: CollectorMessage to send
        """
        await self._message_queue.put(message)

    async def _message_generator(
        self,
    ) -> AsyncIterator[ecg_streaming_pb2.CollectorMessage]:
        """Generate messages to send to aggregator.

        Yields:
            CollectorMessages from queue
        """
        try:
            # Send registration first
            registration = ecg_streaming_pb2.CollectorRegistration(
                collector_id=self.collector_id,
                device_ids=self.device_ids,
                display_name=self.display_name,
                metadata=self.metadata,
            )

            reg_msg = ecg_streaming_pb2.CollectorMessage()
            reg_msg.registration.CopyFrom(registration)
            yield reg_msg

            logger.info(f"Sent registration for collector: {self.collector_id}")

            # Send queued messages
            while self._running:
                try:
                    # Get next message with timeout to allow heartbeats
                    message = await asyncio.wait_for(self._message_queue.get(), timeout=10.0)
                    yield message

                except TimeoutError:
                    # Send heartbeat if no messages for 10 seconds
                    if time.time() - self._last_heartbeat > 10.0:
                        heartbeat = ecg_streaming_pb2.CollectorHeartbeat(
                            timestamp_ms=int(time.time() * 1000),
                            samples_sent=0,  # Could be tracked by caller
                            active_devices=len(self.device_ids),
                        )

                        hb_msg = ecg_streaming_pb2.CollectorMessage()
                        hb_msg.heartbeat.CopyFrom(heartbeat)
                        yield hb_msg

                        self._last_heartbeat = time.time()
        finally:
            pass

    async def _stream_loop(self) -> None:
        """Main streaming loop."""
        if not self._stub:
            logger.error("gRPC stub not initialized")
            return

        try:
            # Start bidirectional stream
            response_stream = self._stub.StreamECG(self._message_generator())

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
                        self._running = False
                        break

                elif msg_type == "sync_status":
                    # Could handle time sync here
                    pass

                elif msg_type == "control":
                    # Could handle control commands here
                    logger.info(f"Received control command: {response.control}")

        except grpc.RpcError as e:
            logger.error(f"gRPC stream error: {e}")
            self._connected = False

        except Exception as e:
            logger.error(f"Stream loop error: {e}", exc_info=True)
            self._connected = False
        finally:
            pass

    async def run(self) -> None:
        """Run the gRPC client."""
        self._running = True

        # Connect to aggregator
        if not await self.connect():
            logger.error("Failed to connect to aggregator")
            return

        # Run stream loop
        try:
            await self._stream_loop()
        finally:
            await self.disconnect()

    @property
    def connected(self) -> bool:
        """Check if connected to aggregator.

        Returns:
            True if connected
        """
        return self._connected
