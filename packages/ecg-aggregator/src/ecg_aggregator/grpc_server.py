"""gRPC server for receiving ECG data from collectors."""

import asyncio
import contextlib
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import grpc
from ecg_common import DeviceStatus, DeviceStatusCode
from ecg_common.logging import get_logger
from ecg_common.proto import collector_aggregator_pb2, collector_aggregator_pb2_grpc

from ecg_aggregator.api.data_buffer import AccelerometerDataBuffer, ECGDataBuffer
from ecg_aggregator.api.sse_broadcaster import SSEBroadcaster
from ecg_aggregator.storage.persistence import ECGDatabase
from ecg_aggregator.sync.calibration_manager import CalibrationManager
from ecg_aggregator.sync.spike_detector import AccSample
from ecg_aggregator.sync.time_alignment import TimeAlignmentService

if TYPE_CHECKING:
    from ecg_aggregator.api.server import ECGStreamingServer

logger = get_logger(__name__)


@dataclass
class CollectorMetadata:
    """Metadata for a connected collector."""

    collector_id: str
    display_name: str
    device_ids: list[str]
    version: str
    metadata: dict[str, str]
    connected_at: float
    last_heartbeat: float
    samples_sent: int = 0
    active_devices: int = 0


@dataclass
class DeviceRuntimeStatus:
    """Status information for a device."""

    device_id: str
    collector_id: str
    status: DeviceStatus = DeviceStatus.DISCONNECTED
    last_update: float = field(default_factory=time.time)
    last_data_time: float | None = None
    battery_level: int | None = None
    error_message: str | None = None


class ECGStreamingServicer(collector_aggregator_pb2_grpc.ECGStreamingServiceServicer):
    """gRPC servicer for ECG streaming."""

    def __init__(
        self,
        time_alignment: TimeAlignmentService,
        ecg_buffer: ECGDataBuffer,
        acc_buffer: AccelerometerDataBuffer,
        database: ECGDatabase | None = None,
        calibration_manager: CalibrationManager | None = None,
        sse_broadcaster: SSEBroadcaster | None = None,
        http_server: ECGStreamingServer | None = None,
    ):
        """Initialize the servicer.

        Args:
            time_alignment: Time alignment service
            ecg_buffer: ECG data buffer for recent samples
            acc_buffer: Accelerometer data buffer for recent samples
            database: Optional database for persistence
            calibration_manager: Optional calibration manager for device alignment
            sse_broadcaster: Optional SSE broadcaster for status updates
            http_server: Optional HTTP server for calibration broadcasts
        """
        self.time_alignment = time_alignment
        self.ecg_buffer = ecg_buffer
        self.acc_buffer = acc_buffer
        self.database = database
        self.calibration_manager = calibration_manager
        self.sse_broadcaster = sse_broadcaster
        self.http_server = http_server

        # Track connected collectors
        self.collectors: dict[str, CollectorMetadata] = {}

        # Track device statuses
        self.device_statuses: dict[str, DeviceRuntimeStatus] = {}

        # Active session tracking
        self._active_session_id: int | None = None
        self._active_session_start_time: float | None = None

        # Statistics
        self._samples_received = 0
        self._acc_samples_received = 0
        self._last_frame_ts: dict[tuple[str, str], int] = {}
        self._sync_ready_logged: dict[str, int] = {}

        # Sample batching for database writes
        self._ecg_batch_buffer: list[
            tuple[str, float, float, int, float, int | None, int | None, int | None, bool]
        ] = []
        self._acc_batch_buffer: list[
            tuple[
                str,
                float,
                float,
                float,
                float,
                float,
                float,
                int | None,
                int | None,
                int | None,
                bool,
            ]
        ] = []
        self._last_flush_time = time.time()
        self._flush_lock = asyncio.Lock()
        self._flush_task: asyncio.Task | None = None

        # Batching configuration
        self._batch_size_threshold = 750  # Flush when buffer reaches this size
        self._batch_time_threshold = 0.5  # Flush at least every 0.5 seconds

    async def _flush_sample_batches(self, force: bool = False) -> None:
        """Flush accumulated samples to database.

        Args:
            force: If True, flush regardless of thresholds
        """
        if not self.database:
            return

        async with self._flush_lock:
            current_time = time.time()
            time_since_flush = current_time - self._last_flush_time

            # Check if we should flush
            should_flush = force or (
                (len(self._ecg_batch_buffer) + len(self._acc_batch_buffer))
                >= self._batch_size_threshold
                or time_since_flush >= self._batch_time_threshold
            )

            if not should_flush:
                return

            # Flush ECG samples
            if self._ecg_batch_buffer:
                ecg_count = len(self._ecg_batch_buffer)
                try:
                    # Execute in thread pool to avoid blocking async event loop
                    flush_start = time.time()
                    await asyncio.get_event_loop().run_in_executor(
                        None, self.database.add_samples_batch, self._ecg_batch_buffer.copy()
                    )
                    flush_duration = time.time() - flush_start
                    self._ecg_batch_buffer.clear()
                    logger.info(
                        f"Flushed {ecg_count} ECG samples to DB in {flush_duration:.3f}s (buffer wait: {time_since_flush:.2f}s)"
                    )
                except Exception as e:
                    logger.error(f"Error flushing ECG batch: {e}")

            # Flush ACC samples
            if self._acc_batch_buffer:
                acc_count = len(self._acc_batch_buffer)
                try:
                    # Execute in thread pool to avoid blocking async event loop
                    flush_start = time.time()
                    await asyncio.get_event_loop().run_in_executor(
                        None, self.database.add_acc_samples_batch, self._acc_batch_buffer.copy()
                    )
                    flush_duration = time.time() - flush_start
                    self._acc_batch_buffer.clear()
                    logger.info(f"Flushed {acc_count} ACC samples to DB in {flush_duration:.3f}s")
                except Exception as e:
                    logger.error(f"Error flushing ACC batch: {e}")

            self._last_flush_time = current_time

    async def _periodic_flush_task(self) -> None:
        """Background task to periodically flush sample batches."""
        try:
            while True:
                await asyncio.sleep(self._batch_time_threshold)
                await self._flush_sample_batches()
        except asyncio.CancelledError:
            # Flush any remaining samples before exiting
            logger.info("Periodic flush task cancelled, flushing remaining samples...")
            await self._flush_sample_batches(force=True)
            raise

    def start_flush_task(self) -> None:
        """Start the periodic flush background task."""
        if self._flush_task is None or self._flush_task.done():
            self._flush_task = asyncio.create_task(self._periodic_flush_task())
            logger.info("Started periodic flush task")

    async def stop_flush_task(self) -> None:
        """Stop the periodic flush background task and flush remaining samples."""
        if self._flush_task and not self._flush_task.done():
            self._flush_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._flush_task
            logger.info("Stopped periodic flush task")

    async def StreamECG(  # noqa: N802
        self,
        request_iterator: AsyncIterator[collector_aggregator_pb2.CollectorMessage],
        context: grpc.aio.ServicerContext,
    ) -> AsyncIterator[collector_aggregator_pb2.AggregatorMessage]:
        """Handle bidirectional streaming of ECG data.

        Args:
            request_iterator: Stream of messages from collector
            context: gRPC context

        Yields:
            Messages to send back to collector
        """
        collector_id: str | None = None
        device_ids: list[str] = []
        try:
            async for message in request_iterator:
                msg_type = message.WhichOneof("message")

                # Update last_heartbeat on ANY message from collector
                # This proves the collector is alive and processing
                if collector_id and collector_id in self.collectors:
                    self.collectors[collector_id].last_heartbeat = time.time()

                if msg_type == "registration":
                    # Handle collector registration
                    reg = message.registration
                    collector_id = reg.collector_id
                    device_ids = list(reg.device_ids)
                    display_name = reg.display_name or collector_id

                    logger.info(
                        f"Collector {display_name} ({collector_id}) registered with {len(device_ids)} devices"
                    )
                    if device_ids:
                        logger.info(f"  Devices: {', '.join(device_ids)}")

                    now = time.time()
                    self.collectors[collector_id] = CollectorMetadata(
                        collector_id=collector_id,
                        display_name=display_name,
                        device_ids=device_ids,
                        version=reg.version,
                        metadata=dict(reg.metadata),
                        connected_at=now,
                        last_heartbeat=now,
                        samples_sent=0,
                        active_devices=0,
                    )

                    # Broadcast collector connection via SSE
                    if self.sse_broadcaster:
                        from ecg_aggregator.api.sse_broadcaster import CollectorUpdateData

                        asyncio.create_task(
                            self.sse_broadcaster.broadcast(
                                "collector_update",
                                CollectorUpdateData(
                                    collector_id=collector_id,
                                    display_name=display_name,
                                    status="CONNECTED",
                                    active_devices=0,
                                ),
                            )
                        )

                    # Persist collector to database
                    if self.database:
                        self.database.upsert_collector(
                            collector_id=collector_id,
                            display_name=display_name,
                            version=reg.version,
                            metadata=dict(reg.metadata),
                        )

                        # Ensure all devices exist in database and persist mappings
                        for device_id in device_ids:
                            # Get or create device entry (creates if doesn't exist)
                            self.database._get_or_create_device_id(device_id)

                            # Persist device-collector mapping
                            self.database.upsert_device_collector_mapping(
                                device_id=device_id, collector_id=collector_id
                            )

                        # Update device nicknames from collector config
                        if reg.device_nicknames:
                            for device_id, nickname in reg.device_nicknames.items():
                                if nickname:  # Only update if nickname is non-empty
                                    self.database.update_device_nickname(device_id, nickname)
                                    logger.info(
                                        f"Set nickname for {device_id} to '{nickname}' from collector config"
                                    )

                    # Initialize device statuses for all configured devices
                    for device_id in device_ids:
                        if device_id not in self.device_statuses:
                            self.device_statuses[device_id] = DeviceRuntimeStatus(
                                device_id=device_id,
                                collector_id=collector_id,
                                status=DeviceStatus.DISCONNECTED,
                                last_update=time.time(),
                                last_data_time=None,
                                battery_level=None,
                                error_message=None,
                            )
                        else:
                            # Device already known, update collector_id
                            self.device_statuses[device_id].collector_id = collector_id
                            self.device_statuses[device_id].last_update = time.time()

                    # Send registration acknowledgment
                    ack = collector_aggregator_pb2.RegistrationAck(
                        accepted=True,
                        message=f"Collector {collector_id} registered successfully",
                        server_time_ms=int(time.time() * 1000),
                    )

                    yield collector_aggregator_pb2.AggregatorMessage(registration_ack=ack)

                elif msg_type == "ecg_batch":
                    # Handle ECG sample batch
                    batch = message.ecg_batch
                    device_id = batch.device_id

                    # Process the batch
                    await self._process_ecg_batch(device_id, batch)

                    self._samples_received += len(batch.samples)

                    # Track samples_sent for this collector
                    if collector_id and collector_id in self.collectors:
                        self.collectors[collector_id].samples_sent += len(batch.samples)

                    # Track last data time for this device
                    if device_id not in self.device_statuses:
                        self.device_statuses[device_id] = DeviceRuntimeStatus(
                            device_id=device_id,
                            collector_id=collector_id or "",
                        )
                    self.device_statuses[device_id].last_data_time = time.time()

                    # Update active_devices count for this collector
                    if collector_id and collector_id in self.collectors:
                        self._update_active_devices_count(collector_id)

                    # Send sync status update if ready
                    if self.time_alignment.is_device_ready(device_id):
                        state = self.time_alignment._device_models.get(device_id)
                        if state and state.model:
                            last_version = self._sync_ready_logged.get(device_id)
                            if last_version != state.offset_version:
                                self._sync_ready_logged[device_id] = state.offset_version
                                logger.info(
                                    "Time sync ready for %s: offset=%.3fs, confidence=%.2f",
                                    device_id,
                                    state.model.offset,
                                    state.model.confidence,
                                )
                            sync_status = collector_aggregator_pb2.SyncStatusUpdate(
                                device_id=device_id,
                                sync_ready=True,
                                offset_s=state.model.offset,
                                offset_version=state.offset_version,
                                confidence=state.model.confidence,
                            )

                            yield collector_aggregator_pb2.AggregatorMessage(
                                sync_status=sync_status
                            )

                elif msg_type == "acc_batch":
                    # Handle accelerometer sample batch
                    batch = message.acc_batch
                    device_id = batch.device_id
                    logger.debug(
                        f"[FLOW] Received ACC batch from {device_id}: {len(batch.samples)} samples"
                    )

                    # Process the batch
                    await self._process_acc_batch(device_id, batch)

                    self._acc_samples_received += len(batch.samples)

                    # Track samples_sent for this collector (ACC samples too)
                    if collector_id and collector_id in self.collectors:
                        self.collectors[collector_id].samples_sent += len(batch.samples)

                    # Track last data time for this device
                    if device_id not in self.device_statuses:
                        self.device_statuses[device_id] = DeviceRuntimeStatus(
                            device_id=device_id,
                            collector_id=collector_id or "",
                        )
                    self.device_statuses[device_id].last_data_time = time.time()

                    # Update active_devices count for this collector
                    if collector_id and collector_id in self.collectors:
                        self._update_active_devices_count(collector_id)

                elif msg_type == "status_update":
                    # Handle device status update
                    status = message.status_update
                    device_id = status.device_id

                    # Map proto enum to string
                    status_map = {
                        DeviceStatusCode.UNKNOWN.value: DeviceStatus.UNKNOWN,
                        DeviceStatusCode.DISCONNECTED.value: DeviceStatus.DISCONNECTED,
                        DeviceStatusCode.CONNECTING.value: DeviceStatus.CONNECTING,
                        DeviceStatusCode.CONNECTED.value: DeviceStatus.CONNECTED,
                        DeviceStatusCode.STREAMING.value: DeviceStatus.STREAMING,
                        DeviceStatusCode.ERROR.value: DeviceStatus.ERROR,
                    }
                    status_name = status_map.get(status.status, DeviceStatus.UNKNOWN)

                    # Update device status
                    if device_id not in self.device_statuses:
                        self.device_statuses[device_id] = DeviceRuntimeStatus(
                            device_id=device_id,
                            collector_id=collector_id or "",
                        )

                    dev_status = self.device_statuses[device_id]
                    dev_status.status = status_name
                    dev_status.last_update = time.time()
                    dev_status.battery_level = (
                        status.battery_level if status.HasField("battery_level") else None
                    )
                    dev_status.error_message = (
                        status.error_message if status.HasField("error_message") else None
                    )

                    # Broadcast device status update via SSE
                    if self.sse_broadcaster and collector_id:
                        from ecg_aggregator.api.sse_broadcaster import DeviceUpdateData

                        device_update = DeviceUpdateData(
                            device_id=device_id,
                            collector_id=collector_id,
                            status=status_name,
                            battery_level=status.battery_level
                            if status.HasField("battery_level")
                            else None,
                        )

                        asyncio.create_task(
                            self.sse_broadcaster.broadcast("device_update", device_update)
                        )

                    logger.debug(f"Status update from {device_id}: {status_name}")

                elif msg_type == "ble_debug":
                    dbg = message.ble_debug
                    logger.debug(
                        "BLE debug from %s: frame=0x%02X pmd=0x%02X len=%d samples=%d polar_clock_us=%d interval_us=%d idx=%d",
                        dbg.device_id or "<unknown>",
                        dbg.frame_type,
                        dbg.pmd_type,
                        dbg.notif_len,
                        dbg.sample_count,
                        dbg.polar_clock_us,
                        dbg.interval_us,
                        dbg.notification_index,
                    )

                # Heartbeat messages are no longer needed - we track last_heartbeat
                # on ANY message from the collector (see above)
                elif msg_type == "heartbeat":
                    # Deprecated: Heartbeat tracking now happens automatically on all messages
                    logger.debug(f"Received legacy heartbeat from {collector_id} (ignored)")

        except asyncio.CancelledError:
            logger.info(f"Stream cancelled for collector {collector_id}")
            raise

        except Exception as e:
            logger.error(f"Error in stream for collector {collector_id}: {e}")
            await context.abort(grpc.StatusCode.INTERNAL, str(e))

        finally:
            if collector_id and collector_id in self.collectors:
                logger.info(f"Collector {collector_id} disconnected")

                # Mark all devices from this collector as disconnected
                for _device_id, dev_status in self.device_statuses.items():
                    if dev_status.collector_id == collector_id:
                        dev_status.status = DeviceStatus.DISCONNECTED
                        dev_status.last_update = time.time()

                        # Broadcast device disconnection via SSE
                        if self.sse_broadcaster:
                            from ecg_aggregator.api.sse_broadcaster import DeviceUpdateData

                            asyncio.create_task(
                                self.sse_broadcaster.broadcast(
                                    "device_update",
                                    DeviceUpdateData(
                                        device_id=_device_id,
                                        collector_id=collector_id,
                                        status=DeviceStatus.DISCONNECTED,
                                    ),
                                )
                            )

                # Broadcast collector disconnection via SSE
                if self.sse_broadcaster:
                    from ecg_aggregator.api.sse_broadcaster import CollectorUpdateData

                    asyncio.create_task(
                        self.sse_broadcaster.broadcast(
                            "collector_update",
                            CollectorUpdateData(
                                collector_id=collector_id,
                                status="DISCONNECTED",
                            ),
                        )
                    )

                del self.collectors[collector_id]

    async def _process_ecg_batch(
        self, device_id: str, batch: collector_aggregator_pb2.ECGBatch
    ) -> None:
        """Process an ECG sample batch with structured samples.

        Args:
            device_id: Device identifier
            batch: Protocol buffer ECG batch with structured samples
        """
        process_start = time.time()
        if not batch.samples:
            return

        # Add timestamp pair using last sample's polar clock and wall clock
        # NOTE: batch.wall_clock_us contains collector's epoch timestamp (wall clock time)
        last_sample = batch.samples[-1]
        last_key = (device_id, "ecg")
        prev_ts = self._last_frame_ts.get(last_key)
        if prev_ts is not None:
            sample_count = len(batch.samples)
            expected_span_us = (
                int((sample_count - 1) * 1_000_000 / batch.sample_rate)
                if sample_count > 1 and batch.sample_rate > 0
                else 0
            )
            delta_us = last_sample.polar_clock_us - prev_ts
            gap_threshold_us = max(500_000, expected_span_us * 2)
            if delta_us > gap_threshold_us:
                logger.warning(
                    "Aggregator gap detected %s ECG: delta_us=%d expected_span_us=%d samples=%d",
                    device_id,
                    delta_us,
                    expected_span_us,
                    sample_count,
                )
        self._last_frame_ts[last_key] = last_sample.polar_clock_us
        wall_clock_s = batch.wall_clock_us / 1_000_000.0

        logger.debug(
            f"[TIME_SYNC] Adding timestamp pair: device={device_id}, "
            f"polar_clock_us={last_sample.polar_clock_us}, host_time={wall_clock_s:.3f}"
        )
        self.time_alignment.add_timestamp_pair(
            device_id=device_id,
            device_timestamp=last_sample.polar_clock_us,
            host_receive_time=wall_clock_s,
            sensor_type="ecg",
        )

        # Process each sample (samples already have individual timestamps)
        samples_added = 0
        samples_low_confidence = 0
        samples_no_sync = 0
        for sample in batch.samples:
            # Synchronize timestamp
            synced = self.time_alignment.sync_timestamp(
                device_id=device_id, device_timestamp=sample.polar_clock_us
            )

            if not synced:
                samples_no_sync += 1
                continue

            # Only add to buffer if sync confidence is high enough
            if synced.confidence >= 0.8:
                self.ecg_buffer.add_sample(
                    device_id=device_id,
                    global_time=synced.global_time,
                    raw_value=sample.value,
                    confidence=synced.confidence,
                    wall_clock_us=sample.wall_clock_us,
                    polar_clock_us=sample.polar_clock_us,
                    receiver_clock_us=sample.receiver_clock_us,
                    time_verified=sample.time_verified,
                )
                samples_added += 1
            else:
                samples_low_confidence += 1

            # Accumulate sample for batch database write
            if self.database and self._active_session_id is not None:
                confidence = synced.confidence if synced else 0.0
                # NOTE: synced should always exist here due to continue above, but use wall_clock_s as fallback
                global_time = synced.global_time if synced else wall_clock_s

                # Only assign session_id if sample timestamp is within session bounds
                session_id = None
                if (
                    self._active_session_start_time is not None
                    and global_time >= self._active_session_start_time
                ):
                    session_id = self._active_session_id

                # Add to batch buffer instead of writing immediately
                self._ecg_batch_buffer.append(
                    (
                        device_id,
                        global_time,
                        sample.polar_clock_us,
                        sample.value,
                        confidence,
                        session_id,
                        sample.wall_clock_us,
                        sample.receiver_clock_us,
                        sample.time_verified,
                    )
                )

        # Check if we should flush batched samples
        await self._flush_sample_batches()

        process_duration = (time.time() - process_start) * 1000
        if samples_no_sync > 0 or samples_low_confidence > 0:
            logger.warning(
                f"[FLOW] ECG batch from {device_id}: {len(batch.samples)} received, {samples_added} added, "
                f"{samples_no_sync} no sync, {samples_low_confidence} low confidence"
            )
        else:
            logger.debug(
                f"[FLOW] Received ECG batch from {device_id}: {len(batch.samples)} samples, "
                f"added {samples_added} to buffer, processing took {process_duration:.1f}ms"
            )
        if process_duration > 50:
            logger.warning(
                f"[FLOW] Slow ECG batch processing for {device_id}: {process_duration:.1f}ms "
                f"for {len(batch.samples)} samples"
            )

    async def _process_acc_batch(
        self, device_id: str, batch: collector_aggregator_pb2.AccelerometerBatch
    ) -> None:
        """Process an accelerometer sample batch with structured samples.

        Args:
            device_id: Device identifier
            batch: Protocol buffer ACC batch with structured samples
        """
        process_start = time.time()
        if not batch.samples:
            return

        # Add timestamp pair using last sample's polar clock and wall clock
        # NOTE: batch.wall_clock_us contains collector's epoch timestamp (wall clock time)
        last_sample = batch.samples[-1]
        last_key = (device_id, "acc")
        prev_ts = self._last_frame_ts.get(last_key)
        if prev_ts is not None:
            sample_count = len(batch.samples)
            expected_span_us = (
                int((sample_count - 1) * 1_000_000 / batch.sample_rate)
                if sample_count > 1 and batch.sample_rate > 0
                else 0
            )
            delta_us = last_sample.polar_clock_us - prev_ts
            gap_threshold_us = max(500_000, expected_span_us * 2)
            if delta_us > gap_threshold_us:
                logger.warning(
                    "Aggregator gap detected %s ACC: delta_us=%d expected_span_us=%d samples=%d",
                    device_id,
                    delta_us,
                    expected_span_us,
                    sample_count,
                )
        self._last_frame_ts[last_key] = last_sample.polar_clock_us
        wall_clock_s = batch.wall_clock_us / 1_000_000.0

        logger.debug(
            f"[TIME_SYNC] Adding timestamp pair: device={device_id}, "
            f"polar_clock_us={last_sample.polar_clock_us}, host_time={wall_clock_s:.3f}"
        )
        self.time_alignment.add_timestamp_pair(
            device_id=device_id,
            device_timestamp=last_sample.polar_clock_us,
            host_receive_time=wall_clock_s,
            sensor_type="acc",
        )

        # Process each sample (samples already have individual timestamps and x,y,z values)
        samples_added = 0
        for sample in batch.samples:
            # Synchronize timestamp
            synced = self.time_alignment.sync_timestamp(
                device_id=device_id, device_timestamp=sample.polar_clock_us
            )

            # Only add to buffer if sync confidence is high enough
            if synced and synced.confidence >= 0.8:
                self.acc_buffer.add_sample(
                    device_id=device_id,
                    global_time=synced.global_time,
                    x=sample.x,
                    y=sample.y,
                    z=sample.z,
                    confidence=synced.confidence,
                    wall_clock_us=sample.wall_clock_us,
                    polar_clock_us=sample.polar_clock_us,
                    receiver_clock_us=sample.receiver_clock_us,
                    time_verified=sample.time_verified,
                )
                samples_added += 1

            # Pass to calibration manager for spike detection (if active session)
            if self.calibration_manager and synced:
                # Compute magnitude
                import math

                magnitude = math.sqrt(sample.x**2 + sample.y**2 + sample.z**2)

                # Create AccSample for calibration
                acc_sample = AccSample(
                    device_id=device_id,
                    global_time=synced.global_time,
                    device_timestamp=sample.polar_clock_us,
                    x=sample.x,
                    y=sample.y,
                    z=sample.z,
                    magnitude=magnitude,
                )

                # Process sample through calibration (detects taps, updates alignments)
                tap_event, alignment = self.calibration_manager.process_acc_sample(acc_sample)

                # Broadcast tap detection and alignment updates via WebSocket
                if tap_event and self.http_server:
                    await self.http_server.broadcast_calibration_event(
                        "tap_detected",
                        {
                            "device_id": tap_event.device_id,
                            "tap_timestamp": tap_event.tap_timestamp,
                            "magnitude": tap_event.magnitude,
                            "confidence": tap_event.confidence,
                        },
                    )

                if alignment and self.http_server:
                    await self.http_server.broadcast_calibration_event(
                        "alignment_updated",
                        {
                            "device_id": alignment.device_id,
                            "status": alignment.status,
                            "confidence": alignment.confidence,
                            "offset": alignment.time_offset,
                            "tap_count": alignment.tap_count,
                            "mean_error": alignment.mean_error,
                            "std_error": alignment.std_error,
                            "ready": alignment.status == "aligned" and alignment.confidence >= 0.8,
                        },
                    )

            # Accumulate sample for batch database write
            if self.database and self._active_session_id is not None:
                confidence = synced.confidence if synced else 0.0
                # NOTE: synced should always exist here due to continue above, but use wall_clock_s as fallback
                global_time = synced.global_time if synced else wall_clock_s

                # Only assign session_id if sample timestamp is within session bounds
                session_id = None
                if (
                    self._active_session_start_time is not None
                    and global_time >= self._active_session_start_time
                ):
                    session_id = self._active_session_id

                # Add to batch buffer instead of writing immediately
                self._acc_batch_buffer.append(
                    (
                        device_id,
                        global_time,
                        sample.polar_clock_us,
                        sample.x,
                        sample.y,
                        sample.z,
                        confidence,
                        session_id,
                        sample.wall_clock_us,
                        sample.receiver_clock_us,
                        sample.time_verified,
                    )
                )

        # Check if we should flush batched samples
        await self._flush_sample_batches()

        process_duration = (time.time() - process_start) * 1000
        # Use same debug log as ECG for consistency, but already logged above with [FLOW] prefix
        if process_duration > 50:
            logger.warning(
                f"[FLOW] Slow ACC batch processing for {device_id}: {process_duration:.1f}ms "
                f"for {len(batch.samples)} samples"
            )

    def start_session(self, notes: str | None = None) -> int:
        """Start a new recording session.

        Args:
            notes: Optional session notes

        Returns:
            Session ID, or -1 if failed or session already active
        """
        if self._active_session_id is not None:
            logger.warning(
                f"Cannot start new session: session {self._active_session_id} is already active"
            )
            return -1

        if not self.database:
            logger.error("Cannot start session: no database configured")
            return -1

        session_id = self.database.create_session(notes=notes)

        if session_id != -1:
            # Fetch the session to get its start_time
            session = self.database.get_session(session_id)
            if session:
                self._active_session_id = session_id
                self._active_session_start_time = session["start_time"]
                active_devices = [
                    dev_id
                    for dev_id, dev_status in self.device_statuses.items()
                    if dev_status.status == DeviceStatus.STREAMING
                ]
                logger.info(
                    f"Started session {session_id} with {len(active_devices)} streaming devices"
                )
                if active_devices:
                    logger.info(f"  Streaming: {', '.join(active_devices)}")
            else:
                logger.error(f"Failed to fetch session {session_id} after creation")
                return -1

        return session_id

    def stop_session(self) -> int | None:
        """Stop the currently active recording session.

        Returns:
            Session ID that was stopped, or None if no session was active
        """
        if self._active_session_id is None:
            logger.warning("Cannot stop session: no active session")
            return None

        if not self.database:
            logger.error("Cannot stop session: no database configured")
            return None

        # End the session in the database
        success = self.database.end_session(self._active_session_id)

        if success:
            stopped_session_id = self._active_session_id
            # Get session stats before clearing
            session = self.database.get_session(stopped_session_id)
            self._active_session_id = None
            self._active_session_start_time = None

            if session:
                duration = session.get("duration_seconds", 0)
                ecg_count = session.get("ecg_sample_count", 0)
                acc_count = session.get("acc_sample_count", 0)
                device_count = session.get("device_count", 0)
                logger.info(
                    f"Stopped session {stopped_session_id}: {duration:.1f}s, {device_count} devices, "
                    f"{ecg_count} ECG samples, {acc_count} ACC samples"
                )
            else:
                logger.info(f"Stopped recording session {stopped_session_id}")

            return stopped_session_id

        return None

    def get_active_session_id(self) -> int | None:
        """Get the currently active session ID.

        Returns:
            Active session ID, or None if no session is active
        """
        return self._active_session_id

    def _update_active_devices_count(self, collector_id: str) -> None:
        """Update the active_devices count for a collector.

        Counts devices that have sent data within the last 30 seconds.

        Args:
            collector_id: Collector ID to update count for
        """
        if collector_id not in self.collectors:
            return

        now = time.time()
        active_window_s = 30.0  # Consider devices active if they sent data in last 30s

        active_count = sum(
            1
            for dev_id, dev_status in self.device_statuses.items()
            if dev_status.collector_id == collector_id
            and dev_status.last_data_time is not None
            and (now - dev_status.last_data_time) <= active_window_s
        )

        self.collectors[collector_id].active_devices = active_count

    def get_active_device_count(self, active_window_s: float = 30.0) -> int:
        """Get total number of active devices across all collectors."""
        now = time.time()
        return sum(
            1
            for dev_status in self.device_statuses.values()
            if dev_status.last_data_time is not None
            and (now - dev_status.last_data_time) <= active_window_s
        )

    def get_stats(self) -> dict:
        """Get server statistics.

        Returns:
            Dictionary containing server statistics
        """
        return {
            "collectors_connected": len(self.collectors),
            "collectors": list(self.collectors.keys()),
            "samples_received": self._samples_received,
            "acc_samples_received": self._acc_samples_received,
            "active_session_id": self._active_session_id,
        }


async def serve(
    time_alignment: TimeAlignmentService,
    ecg_buffer: ECGDataBuffer,
    acc_buffer: AccelerometerDataBuffer,
    database: ECGDatabase | None = None,
    port: int = 50051,
) -> None:
    """Start the gRPC server.

    Args:
        time_alignment: Time alignment service
        ecg_buffer: ECG data buffer
        acc_buffer: Accelerometer data buffer
        database: Optional database
        port: Server port
    """
    server = grpc.aio.server()

    servicer = ECGStreamingServicer(
        time_alignment=time_alignment,
        ecg_buffer=ecg_buffer,
        acc_buffer=acc_buffer,
        database=database,
    )

    collector_aggregator_pb2_grpc.add_ECGStreamingServiceServicer_to_server(servicer, server)

    listen_addr = f"[::]:{port}"
    server.add_insecure_port(listen_addr)

    logger.info(f"Starting gRPC server on {listen_addr}")
    await server.start()

    try:
        await server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("Shutting down gRPC server...")
        await server.stop(grace=5)
