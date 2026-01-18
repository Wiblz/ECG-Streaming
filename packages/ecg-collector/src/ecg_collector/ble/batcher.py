"""Sample batcher for BLE collectors.

Accumulates individual ECG and accelerometer samples into batches for efficient transmission.
"""

import asyncio
import contextlib
import time
from collections.abc import Callable, Coroutine

from ecg_common.logging import get_logger
from ecg_common.models import AccelerometerSample, DeviceStatus, ECGSample
from ecg_common.proto import ecg_streaming_pb2

logger = get_logger(__name__)


class SampleBatcher:
    """Batches individual samples into CollectorMessages."""

    def __init__(
        self,
        device_ids: list[str],
        batch_size: int = 50,
        batch_interval: float = 0.1,
        message_callback: Callable[
            [ecg_streaming_pb2.CollectorMessage], Coroutine[None, None, None]
        ]
        | None = None,
    ) -> None:
        """Initialize the sample batcher.

        Args:
            device_ids: List of device IDs to batch samples for
            batch_size: Number of samples per batch
            batch_interval: Interval between batch sends (seconds)
            message_callback: Callback to invoke with batched CollectorMessages
        """
        self.device_ids = device_ids
        self.batch_size = batch_size
        self.batch_interval = batch_interval
        self.message_callback = message_callback

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
        self._status_updates: asyncio.Queue[tuple[str, DeviceStatus, int | None, str | None]] = (
            asyncio.Queue()
        )

        self._running = False
        self._batch_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the batcher."""
        logger.info("Starting sample batcher")
        self._running = True
        self._batch_task = asyncio.create_task(self._batch_loop())

    async def stop(self) -> None:
        """Stop the batcher."""
        logger.info("Stopping sample batcher")
        self._running = False

        if self._batch_task:
            self._batch_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._batch_task

    async def send_sample(self, sample: ECGSample) -> None:
        """Queue an ECG sample for batching.

        Args:
            sample: ECG sample to batch
        """
        if sample.device_id not in self._sample_queues:
            logger.warning(f"Sample from unknown device {sample.device_id}, ignoring")
            return

        await self._sample_queues[sample.device_id].put(sample)

    async def send_acc_sample(self, sample: AccelerometerSample) -> None:
        """Queue an accelerometer sample for batching.

        Args:
            sample: Accelerometer sample to batch
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
        """Update device status and queue it for sending.

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
            await self._status_updates.put((device_id, status, battery_level, error_message))
            logger.info(f"Device {device_id} status queued for update: {status.name}")
        else:
            logger.debug(f"Device {device_id} status unchanged ({status.name}), skipping update")

    async def _batch_loop(self) -> None:
        """Main batching loop."""
        while self._running:
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
                    await self._send_ecg_batch(device_id, samples_batch)

            # Send ACC batches
            for device_id, acc_queue in self._acc_queues.items():
                acc_batch: list[AccelerometerSample] = []

                # Collect up to batch_size samples from this device's queue
                while not acc_queue.empty() and len(acc_batch) < self.batch_size:
                    try:
                        acc_sample = acc_queue.get_nowait()
                        acc_batch.append(acc_sample)
                    except asyncio.QueueEmpty:
                        break

                # Send batch if we have samples
                if acc_batch:
                    batches_ready = True
                    await self._send_acc_batch(device_id, acc_batch)

            # Send queued status updates
            while not self._status_updates.empty():
                try:
                    device_id, status, battery_level, error_message = (
                        self._status_updates.get_nowait()
                    )
                    await self._send_status_update(device_id, status, battery_level, error_message)
                except asyncio.QueueEmpty:
                    break

            # Sleep before next iteration
            await asyncio.sleep(self.batch_interval if batches_ready else 1.0)

    async def _send_ecg_batch(self, device_id: str, samples: list[ECGSample]) -> None:
        """Send an ECG batch via callback.

        Args:
            device_id: Device ID
            samples: List of ECG samples
        """
        if not self.message_callback:
            return

        proto_samples = [
            ecg_streaming_pb2.ECGSample(
                device_timestamp_us=s.device_timestamp,
                host_receive_time_s=s.host_receive_time,
                raw_value=s.raw_value,
                sample_rate=s.sample_rate,
            )
            for s in samples
        ]

        batch = ecg_streaming_pb2.ECGSampleBatch(
            device_id=device_id,
            samples=proto_samples,
            batch_timestamp_ms=int(time.time() * 1000),
        )

        message = ecg_streaming_pb2.CollectorMessage(ecg_batch=batch)
        await self.message_callback(message)

        logger.debug(f"Sent ECG batch of {len(samples)} samples from {device_id}")

    async def _send_acc_batch(self, device_id: str, samples: list[AccelerometerSample]) -> None:
        """Send an accelerometer batch via callback.

        Args:
            device_id: Device ID
            samples: List of accelerometer samples
        """
        if not self.message_callback:
            return

        proto_samples = [
            ecg_streaming_pb2.AccelerometerSample(
                device_timestamp_us=s.device_timestamp,
                host_receive_time_s=s.host_receive_time,
                x=s.x,
                y=s.y,
                z=s.z,
                sample_rate=50,  # Polar H10 ACC sample rate
            )
            for s in samples
        ]

        batch = ecg_streaming_pb2.AccelerometerSampleBatch(
            device_id=device_id,
            samples=proto_samples,
            batch_timestamp_ms=int(time.time() * 1000),
        )

        message = ecg_streaming_pb2.CollectorMessage(acc_batch=batch)
        await self.message_callback(message)

        logger.debug(f"Sent ACC batch of {len(samples)} samples from {device_id}")

    async def _send_status_update(
        self,
        device_id: str,
        status: DeviceStatus,
        battery_level: int | None,
        error_message: str | None,
    ) -> None:
        """Send a status update via callback.

        Args:
            device_id: Device ID
            status: Device status
            battery_level: Optional battery level (0-100)
            error_message: Optional error message
        """
        if not self.message_callback:
            return

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

        message = ecg_streaming_pb2.CollectorMessage(status_update=status_update)
        await self.message_callback(message)

        logger.info(f"Sent status update for {device_id}: {status.name}")
