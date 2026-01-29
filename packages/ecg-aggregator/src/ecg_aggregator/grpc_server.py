"""gRPC server for receiving ECG data from collectors."""

import asyncio
import time
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

import grpc
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
        self.collectors: dict[str, dict] = {}  # collector_id -> metadata

        # Track device statuses
        self.device_statuses: dict[
            str, dict
        ] = {}  # device_id -> {status, collector_id, last_update, ...}

        # Active session tracking
        self._active_session_id: int | None = None
        self._active_session_start_time: float | None = None

        # Statistics
        self._samples_received = 0
        self._acc_samples_received = 0

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
                if msg_type == "registration":
                    # Handle collector registration
                    reg = message.registration
                    collector_id = reg.collector_id
                    device_ids = list(reg.device_ids)
                    display_name = reg.display_name or collector_id

                    logger.info(
                        f"Collector {display_name} ({collector_id}) registered with {len(device_ids)} devices: "
                        f"{', '.join(device_ids)}"
                    )

                    self.collectors[collector_id] = {
                        "collector_id": collector_id,
                        "display_name": display_name,
                        "device_ids": device_ids,
                        "version": reg.version,
                        "metadata": dict(reg.metadata),
                        "connected_at": time.time(),
                        "last_heartbeat": time.time(),
                        "samples_sent": 0,
                        "active_devices": 0,
                    }

                    # Broadcast collector connection via SSE
                    if self.sse_broadcaster:
                        asyncio.create_task(
                            self.sse_broadcaster.broadcast(
                                "collector_update",
                                {
                                    "collector_id": collector_id,
                                    "display_name": display_name,
                                    "status": "CONNECTED",
                                    "device_count": len(device_ids),
                                },
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

                        # Persist device-collector mappings
                        for device_id in device_ids:
                            self.database.upsert_device_collector_mapping(
                                device_id=device_id, collector_id=collector_id
                            )

                    # Initialize device statuses for all configured devices
                    for device_id in device_ids:
                        if device_id not in self.device_statuses:
                            self.device_statuses[device_id] = {
                                "device_id": device_id,
                                "collector_id": collector_id,
                                "status": "DISCONNECTED",  # Initially disconnected
                                "last_update": time.time(),
                                "battery_level": None,
                                "error_message": None,
                            }
                        else:
                            # Device already known, update collector_id
                            self.device_statuses[device_id]["collector_id"] = collector_id
                            self.device_statuses[device_id]["last_update"] = time.time()

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

                    # Send sync status update if ready
                    if self.time_alignment.is_device_ready(device_id):
                        state = self.time_alignment._device_models.get(device_id)
                        if state and state.model:
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

                elif msg_type == "status_update":
                    # Handle device status update
                    status = message.status_update
                    device_id = status.device_id

                    # Map proto enum to string
                    status_map = {
                        0: "UNKNOWN",
                        1: "DISCONNECTED",
                        2: "CONNECTING",
                        3: "CONNECTED",
                        4: "STREAMING",
                        5: "ERROR",
                    }
                    status_str = status_map.get(status.status, "UNKNOWN")

                    # Update device status
                    if device_id not in self.device_statuses:
                        self.device_statuses[device_id] = {
                            "device_id": device_id,
                            "collector_id": collector_id,
                        }

                    self.device_statuses[device_id].update(
                        {
                            "status": status_str,
                            "last_update": time.time(),
                            "battery_level": status.battery_level
                            if status.HasField("battery_level")
                            else None,
                            "error_message": status.error_message
                            if status.HasField("error_message")
                            else None,
                        }
                    )

                    # Broadcast device status update via SSE
                    if self.sse_broadcaster and collector_id:
                        from ecg_aggregator.api.sse_broadcaster import DeviceUpdateData

                        device_update: DeviceUpdateData = {
                            "device_id": device_id,
                            "collector_id": collector_id,
                            "status": status_str,  # type: ignore[typeddict-item]
                        }
                        if status.HasField("battery_level"):
                            device_update["battery_level"] = status.battery_level

                        asyncio.create_task(
                            self.sse_broadcaster.broadcast("device_update", device_update)
                        )

                    logger.debug(f"Status update from {device_id}: {status_str}")

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

                elif msg_type == "heartbeat":
                    # Handle heartbeat
                    hb = message.heartbeat

                    # Update collector heartbeat info
                    if collector_id and collector_id in self.collectors:
                        self.collectors[collector_id]["last_heartbeat"] = time.time()
                        self.collectors[collector_id]["samples_sent"] = hb.samples_sent
                        self.collectors[collector_id]["active_devices"] = hb.active_devices

                        # Persist heartbeat to database
                        if self.database:
                            self.database.update_collector_heartbeat(collector_id)

                        # Broadcast collector heartbeat via SSE (for health status)
                        if self.sse_broadcaster:
                            asyncio.create_task(
                                self.sse_broadcaster.broadcast(
                                    "collector_update",
                                    {
                                        "collector_id": collector_id,
                                        "status": "HEALTHY",
                                        "samples_sent": hb.samples_sent,
                                        "active_devices": hb.active_devices,
                                    },
                                )
                            )

                    logger.debug(
                        f"Heartbeat from {collector_id}: "
                        f"{hb.samples_sent} samples, {hb.active_devices} active devices"
                    )

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
                    if dev_status.get("collector_id") == collector_id:
                        dev_status["status"] = "DISCONNECTED"
                        dev_status["last_update"] = time.time()

                        # Broadcast device disconnection via SSE
                        if self.sse_broadcaster:
                            asyncio.create_task(
                                self.sse_broadcaster.broadcast(
                                    "device_update",
                                    {
                                        "device_id": _device_id,
                                        "collector_id": collector_id,
                                        "status": "DISCONNECTED",
                                    },
                                )
                            )

                # Broadcast collector disconnection via SSE
                if self.sse_broadcaster:
                    asyncio.create_task(
                        self.sse_broadcaster.broadcast(
                            "collector_update",
                            {
                                "collector_id": collector_id,
                                "status": "DISCONNECTED",
                            },
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
        if not batch.samples:
            return

        logger.debug(f"[FLOW] Processing ECG batch from {device_id}: {len(batch.samples)} samples")

        # Add timestamp pair using last sample's polar clock and wall clock
        # NOTE: batch.wall_clock_us contains collector's epoch timestamp (wall clock time)
        last_sample = batch.samples[-1]
        wall_clock_s = batch.wall_clock_us / 1_000_000.0

        self.time_alignment.add_timestamp_pair(
            device_id=device_id,
            device_timestamp=last_sample.polar_clock_us,
            host_receive_time=wall_clock_s,
        )

        # Process each sample (samples already have individual timestamps)
        samples_added = 0
        for sample in batch.samples:
            # Synchronize timestamp
            synced = self.time_alignment.sync_timestamp(
                device_id=device_id, device_timestamp=sample.polar_clock_us
            )

            if not synced:
                logger.debug(f"[FLOW] No sync available for {device_id}")
                continue

            logger.debug(
                f"[FLOW] Synced sample: device_ts={sample.polar_clock_us}, global_time={synced.global_time:.2f}, confidence={synced.confidence}"
            )

            # Only add to buffer if sync confidence is high enough
            if synced and synced.confidence >= 0.8:
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
                logger.debug(f"[FLOW] Skipped sample: confidence {synced.confidence} < 0.8")

            # Store in database only if session is active
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

                self.database.add_sample(
                    device_id=device_id,
                    global_time=global_time,
                    device_timestamp=sample.polar_clock_us,
                    raw_value=sample.value,
                    confidence=confidence,
                    session_id=session_id,
                    wall_clock_us=sample.wall_clock_us,
                    receiver_clock_us=sample.receiver_clock_us,
                    time_verified=sample.time_verified,
                )

        logger.debug(
            f"[FLOW] Added {samples_added}/{len(batch.samples)} samples to buffer for {device_id}"
        )

    async def _process_acc_batch(
        self, device_id: str, batch: collector_aggregator_pb2.AccelerometerBatch
    ) -> None:
        """Process an accelerometer sample batch with structured samples.

        Args:
            device_id: Device identifier
            batch: Protocol buffer ACC batch with structured samples
        """
        if not batch.samples:
            return

        logger.debug(f"[FLOW] Processing ACC batch from {device_id}: {len(batch.samples)} samples")

        # Add timestamp pair using last sample's polar clock and wall clock
        # NOTE: batch.wall_clock_us contains collector's epoch timestamp (wall clock time)
        last_sample = batch.samples[-1]
        wall_clock_s = batch.wall_clock_us / 1_000_000.0

        self.time_alignment.add_timestamp_pair(
            device_id=device_id,
            device_timestamp=last_sample.polar_clock_us,
            host_receive_time=wall_clock_s,
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

            # Store in database only if session is active
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

                self.database.add_acc_sample(
                    device_id=device_id,
                    global_time=global_time,
                    device_timestamp=sample.polar_clock_us,
                    x=sample.x,
                    y=sample.y,
                    z=sample.z,
                    confidence=confidence,
                    session_id=session_id,
                    wall_clock_us=sample.wall_clock_us,
                    receiver_clock_us=sample.receiver_clock_us,
                    time_verified=sample.time_verified,
                )

        logger.debug(
            f"[FLOW] Added {samples_added}/{len(batch.samples)} ACC samples to buffer for {device_id}"
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
                logger.info(f"Started recording session {session_id} at {session['start_time']}")
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
            self._active_session_id = None
            self._active_session_start_time = None
            logger.info(f"Stopped recording session {stopped_session_id}")
            return stopped_session_id

        return None

    def get_active_session_id(self) -> int | None:
        """Get the currently active session ID.

        Returns:
            Active session ID, or None if no session is active
        """
        return self._active_session_id

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
