"""gRPC client for streaming ECG data to the aggregator."""

import asyncio
import contextlib
import time
from collections.abc import AsyncIterator

import grpc
from ecg_common.logging import get_logger
from ecg_common.models import AccelerometerSample, DeviceStatus, ECGSample
from ecg_common.proto import ecg_streaming_pb2, ecg_streaming_pb2_grpc

logger = get_logger(__name__)


class AggregatorClient:
    """gRPC client for connecting to the aggregator and streaming ECG data."""

    def __init__(
        self,
        collector_id: str,
        aggregator_host: str,
        aggregator_port: int,
        device_ids: list[str],
        display_name: str = "",
        batch_size: int = 50,
        batch_interval: float = 0.1,
    ):
        """Initialize the aggregator client.

        Args:
            collector_id: Unique identifier for this collector
            aggregator_host: Aggregator server hostname/IP
            aggregator_port: Aggregator server port
            device_ids: List of device IDs this collector manages
            display_name: Human-readable name for this collector
            batch_size: Number of samples per batch
            batch_interval: Interval between batch sends (seconds)
        """
        self.collector_id = collector_id
        self.display_name = display_name or collector_id
        self.aggregator_host = aggregator_host
        self.aggregator_port = aggregator_port
        self.device_ids = device_ids
        self.batch_size = batch_size
        self.batch_interval = batch_interval

        self._channel: grpc.aio.Channel | None = None
        self._stub: ecg_streaming_pb2_grpc.ECGStreamingServiceStub | None = None
        self._stream_task: asyncio.Task | None = None
        self._reconnect_task: asyncio.Task | None = None
        self._connected = False
        self._should_reconnect = True
        self._connection_failures = 0

        # Sample queues per device
        self._sample_queues: dict[str, asyncio.Queue[ECGSample]] = {
            device_id: asyncio.Queue() for device_id in device_ids
        }
        self._acc_queues: dict[str, asyncio.Queue[AccelerometerSample]] = {
            device_id: asyncio.Queue() for device_id in device_ids
        }

        # Device status tracking (start as UNKNOWN so first update triggers)
        self._device_statuses: dict[str, DeviceStatus] = dict.fromkeys(
            device_ids, DeviceStatus.UNKNOWN
        )

        # Status update queue
        self._status_updates: asyncio.Queue[tuple[str, DeviceStatus]] = asyncio.Queue()

        # Statistics
        self._samples_sent = 0
        self._acc_samples_sent = 0
        self._last_heartbeat = time.time()

    async def connect(self) -> bool:
        """Connect to the aggregator server.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            server_address = f"{self.aggregator_host}:{self.aggregator_port}"
            logger.info(f"Connecting to aggregator at {server_address}")

            self._channel = grpc.aio.insecure_channel(server_address)
            self._stub = ecg_streaming_pb2_grpc.ECGStreamingServiceStub(self._channel)

            # Start the bidirectional stream
            self._stream_task = asyncio.create_task(self._stream_loop())

            # Start reconnection monitoring task
            if not self._reconnect_task or self._reconnect_task.done():
                self._reconnect_task = asyncio.create_task(self._reconnect_loop())

            # Wait a bit to see if connection succeeds
            await asyncio.sleep(0.5)

            if self._connected:
                logger.info(f"Successfully connected to aggregator at {server_address}")
                self._connection_failures = 0
                return True
            else:
                logger.warning(f"Connection to {server_address} pending...")
                return True  # Return True as connection is in progress

        except Exception as e:
            logger.error(f"Failed to connect to aggregator: {e}")
            self._connection_failures += 1
            return False

    async def disconnect(self) -> None:
        """Disconnect from the aggregator server."""
        logger.info("Disconnecting from aggregator...")

        # Stop reconnection attempts
        self._should_reconnect = False

        if self._reconnect_task:
            self._reconnect_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reconnect_task

        if self._stream_task:
            self._stream_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._stream_task

        if self._channel:
            await self._channel.close()

        self._connected = False
        logger.info("Disconnected from aggregator")

    async def send_sample(self, sample: ECGSample) -> None:
        """Queue an ECG sample for sending to the aggregator.

        Args:
            sample: ECG sample to send
        """
        if sample.device_id not in self._sample_queues:
            logger.warning(f"Sample from unknown device {sample.device_id}, ignoring")
            return

        await self._sample_queues[sample.device_id].put(sample)

    async def send_acc_sample(self, sample: AccelerometerSample) -> None:
        """Queue an accelerometer sample for sending to the aggregator.

        Args:
            sample: Accelerometer sample to send
        """
        if sample.device_id not in self._acc_queues:
            logger.warning(f"ACC sample from unknown device {sample.device_id}, ignoring")
            return

        await self._acc_queues[sample.device_id].put(sample)

    async def update_device_status(
        self,
        device_id: str,
        status: DeviceStatus,
        battery_level: int | None = None,
        error_message: str | None = None,
    ) -> None:
        """Update device status and queue it for sending to aggregator.

        Args:
            device_id: Device ID
            status: Device status
            battery_level: Optional battery level (0-100)
            error_message: Optional error message
        """
        if device_id not in self._device_statuses:
            logger.warning(f"Status update for unknown device {device_id}, ignoring")
            return

        # Only send update if status actually changed
        if self._device_statuses[device_id] != status:
            self._device_statuses[device_id] = status
            await self._status_updates.put((device_id, status))
            logger.info(f"Device {device_id} status queued for update: {status.name}")
        else:
            logger.debug(f"Device {device_id} status unchanged ({status.name}), skipping update")

    async def _message_generator(self) -> AsyncIterator[ecg_streaming_pb2.CollectorMessage]:
        """Generate messages to send to the aggregator."""
        # First, send registration
        registration = ecg_streaming_pb2.CollectorRegistration(
            collector_id=self.collector_id,
            device_ids=self.device_ids,
            version="0.1.0",
            metadata={"type": "polar_h10_collector"},
            display_name=self.display_name,
        )

        yield ecg_streaming_pb2.CollectorMessage(registration=registration)

        logger.info(f"Sent registration for collector {self.collector_id}")

        # Then, continuously send sample batches and heartbeats
        while True:
            # Collect samples from all devices into batches
            batches_ready = False

            # Send ECG batches
            for device_id, queue in self._sample_queues.items():
                samples_batch: list[ECGSample] = []

                # Collect up to batch_size samples from this device's queue
                while not queue.empty() and len(samples_batch) < self.batch_size:
                    try:
                        sample = queue.get_nowait()
                        samples_batch.append(sample)
                    except asyncio.QueueEmpty:
                        break

                # Send batch if we have samples
                if samples_batch:
                    batches_ready = True
                    proto_samples = [
                        ecg_streaming_pb2.ECGSample(
                            device_timestamp_us=s.device_timestamp,
                            host_receive_time_s=s.host_receive_time,
                            raw_value=s.raw_value,
                            sample_rate=s.sample_rate,
                        )
                        for s in samples_batch
                    ]

                    batch = ecg_streaming_pb2.ECGSampleBatch(
                        device_id=device_id,
                        samples=proto_samples,
                        batch_timestamp_ms=int(time.time() * 1000),
                    )

                    yield ecg_streaming_pb2.CollectorMessage(ecg_batch=batch)

                    self._samples_sent += len(samples_batch)
                    logger.debug(f"Sent ECG batch of {len(samples_batch)} samples from {device_id}")

            # Send ACC batches
            for device_id, acc_queue in self._acc_queues.items():
                acc_batch: list[AccelerometerSample] = []

                # Collect up to batch_size samples from this device's queue
                while not acc_queue.empty() and len(acc_batch) < self.batch_size:
                    try:
                        acc_sample: AccelerometerSample = acc_queue.get_nowait()
                        acc_batch.append(acc_sample)
                    except asyncio.QueueEmpty:
                        break

                # Send batch if we have samples
                if acc_batch:
                    batches_ready = True
                    proto_samples = [
                        ecg_streaming_pb2.AccelerometerSample(
                            device_timestamp_us=s.device_timestamp,
                            host_receive_time_s=s.host_receive_time,
                            x=s.x,
                            y=s.y,
                            z=s.z,
                            sample_rate=50,  # Polar H10 ACC sample rate
                        )
                        for s in acc_batch
                    ]

                    batch = ecg_streaming_pb2.AccelerometerSampleBatch(
                        device_id=device_id,
                        samples=proto_samples,
                        batch_timestamp_ms=int(time.time() * 1000),
                    )

                    yield ecg_streaming_pb2.CollectorMessage(acc_batch=batch)

                    self._acc_samples_sent += len(acc_batch)
                    logger.debug(f"Sent ACC batch of {len(acc_batch)} samples from {device_id}")

            # Send queued status updates
            while not self._status_updates.empty():
                try:
                    device_id, status = self._status_updates.get_nowait()

                    # Map DeviceStatus enum to protobuf enum value
                    status_map = {
                        DeviceStatus.UNKNOWN: ecg_streaming_pb2.DEVICE_STATUS_UNKNOWN,
                        DeviceStatus.DISCONNECTED: ecg_streaming_pb2.DEVICE_STATUS_DISCONNECTED,
                        DeviceStatus.CONNECTING: ecg_streaming_pb2.DEVICE_STATUS_CONNECTING,
                        DeviceStatus.CONNECTED: ecg_streaming_pb2.DEVICE_STATUS_CONNECTED,
                        DeviceStatus.STREAMING: ecg_streaming_pb2.DEVICE_STATUS_STREAMING,
                        DeviceStatus.ERROR: ecg_streaming_pb2.DEVICE_STATUS_ERROR,
                    }

                    pb_status = status_map.get(status, ecg_streaming_pb2.DEVICE_STATUS_UNKNOWN)

                    status_update = ecg_streaming_pb2.DeviceStatusUpdate(
                        device_id=device_id,
                        status=pb_status,
                    )
                    yield ecg_streaming_pb2.CollectorMessage(status_update=status_update)
                    logger.info(f"Sent status update for {device_id}: {status.name}")

                except asyncio.QueueEmpty:
                    break

            # Send heartbeat periodically
            if time.time() - self._last_heartbeat > 10.0:
                active_devices = sum(
                    1 for q in self._sample_queues.values() if not q.empty()
                ) or sum(1 for q in self._acc_queues.values() if not q.empty())

                heartbeat = ecg_streaming_pb2.CollectorHeartbeat(
                    timestamp_ms=int(time.time() * 1000),
                    samples_sent=self._samples_sent + self._acc_samples_sent,
                    active_devices=active_devices,
                )

                yield ecg_streaming_pb2.CollectorMessage(heartbeat=heartbeat)

                self._last_heartbeat = time.time()
                logger.debug(
                    f"Sent heartbeat: {self._samples_sent} ECG + {self._acc_samples_sent} ACC samples, "
                    f"{active_devices} active devices"
                )

            # Sleep before next iteration
            await asyncio.sleep(self.batch_interval if batches_ready else 1.0)

    async def _stream_loop(self) -> None:
        """Main streaming loop for bidirectional communication."""
        if not self._stub:
            logger.error("gRPC stub not initialized")
            return

        try:
            async for response in self._stub.StreamECG(self._message_generator()):
                await self._handle_aggregator_message(response)

        except grpc.aio.AioRpcError as e:
            logger.error(f"gRPC stream error: {e.code()}: {e.details()}")
            self._connected = False
            self._connection_failures += 1

        except asyncio.CancelledError:
            logger.info("Stream loop cancelled")
            raise

        except Exception as e:
            logger.error(f"Unexpected error in stream loop: {e}")
            self._connected = False
            self._connection_failures += 1

    async def _reconnect_loop(self) -> None:
        """Monitor connection and attempt reconnection when disconnected."""
        try:
            while self._should_reconnect:
                # Wait a bit before checking connection status
                await asyncio.sleep(5.0)

                # If not connected and should reconnect, attempt reconnection
                if not self._connected and self._should_reconnect:
                    # Calculate exponential backoff delay (max 60 seconds)
                    backoff_delay = min(2**self._connection_failures, 60)
                    logger.info(
                        f"Connection lost. Attempting reconnection in {backoff_delay}s "
                        f"(attempt {self._connection_failures + 1})"
                    )
                    await asyncio.sleep(backoff_delay)

                    # Clean up old connection
                    if self._stream_task and not self._stream_task.done():
                        self._stream_task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await self._stream_task

                    if self._channel:
                        await self._channel.close()

                    # Attempt to reconnect
                    try:
                        server_address = f"{self.aggregator_host}:{self.aggregator_port}"
                        self._channel = grpc.aio.insecure_channel(server_address)
                        self._stub = ecg_streaming_pb2_grpc.ECGStreamingServiceStub(self._channel)
                        self._stream_task = asyncio.create_task(self._stream_loop())

                        # Wait to see if connection succeeds
                        await asyncio.sleep(1.0)

                        # Check connection status (can change asynchronously via _stream_loop)
                        if self._connected:
                            logger.info(  # type: ignore[unreachable]  # Modified by concurrent _stream_loop task
                                f"Successfully reconnected to aggregator at {server_address}"
                            )
                            self._connection_failures = 0
                        else:
                            logger.warning(f"Reconnection to {server_address} pending...")

                    except Exception as e:
                        logger.error(f"Reconnection attempt failed: {e}")
                        self._connection_failures += 1

        except asyncio.CancelledError:
            logger.info("Reconnection loop cancelled")
            raise

    async def _handle_aggregator_message(
        self, message: ecg_streaming_pb2.AggregatorMessage
    ) -> None:
        """Handle a message from the aggregator.

        Args:
            message: Message received from aggregator
        """
        msg_type = message.WhichOneof("message")

        if msg_type == "registration_ack":
            ack = message.registration_ack
            if ack.accepted:
                self._connected = True
                logger.info(f"Registration accepted: {ack.message}")
            else:
                logger.error(f"Registration rejected: {ack.message}")
                self._connected = False

        elif msg_type == "sync_status":
            status = message.sync_status
            logger.debug(
                f"Sync status for {status.device_id}: "
                f"ready={status.sync_ready}, offset={status.offset_s:.6f}s, "
                f"confidence={status.confidence:.2f}"
            )

        elif msg_type == "control":
            command = message.control
            logger.info(f"Received control command: {command.command}")
            # TODO: Implement control command handling

        else:
            logger.warning(f"Unknown message type: {msg_type}")

    @property
    def connected(self) -> bool:
        """Check if the client is connected to the aggregator.

        Returns:
            True if connected, False otherwise
        """
        return self._connected

    def get_stats(self) -> dict:
        """Get client statistics.

        Returns:
            Dictionary containing client statistics
        """
        return {
            "connected": self._connected,
            "samples_sent": self._samples_sent,
            "aggregator_host": self.aggregator_host,
            "aggregator_port": self.aggregator_port,
            "collector_id": self.collector_id,
            "device_count": len(self.device_ids),
        }
