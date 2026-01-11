"""gRPC server for receiving ECG data from collectors."""

import asyncio
import time
from collections.abc import AsyncIterator

import grpc
from ecg_common.logging import get_logger
from ecg_common.models import AccelerometerSample, ECGSample
from ecg_common.proto import ecg_streaming_pb2, ecg_streaming_pb2_grpc

from ecg_aggregator.api.data_buffer import AccelerometerDataBuffer, ECGDataBuffer
from ecg_aggregator.storage.persistence import ECGDatabase
from ecg_aggregator.sync.time_alignment import TimeAlignmentService

logger = get_logger(__name__)


class ECGStreamingServicer(ecg_streaming_pb2_grpc.ECGStreamingServiceServicer):
    """gRPC servicer for ECG streaming."""

    def __init__(
        self,
        time_alignment: TimeAlignmentService,
        ecg_buffer: ECGDataBuffer,
        acc_buffer: AccelerometerDataBuffer,
        database: ECGDatabase | None = None,
    ):
        """Initialize the servicer.

        Args:
            time_alignment: Time alignment service
            ecg_buffer: ECG data buffer for recent samples
            acc_buffer: Accelerometer data buffer for recent samples
            database: Optional database for persistence
        """
        self.time_alignment = time_alignment
        self.ecg_buffer = ecg_buffer
        self.acc_buffer = acc_buffer
        self.database = database

        # Track connected collectors
        self.collectors: dict[str, dict] = {}  # collector_id -> metadata

        # Track device statuses
        self.device_statuses: dict[
            str, dict
        ] = {}  # device_id -> {status, collector_id, last_update, ...}

        # Statistics
        self._samples_received = 0
        self._acc_samples_received = 0

    async def StreamECG(  # noqa: N802
        self,
        request_iterator: AsyncIterator[ecg_streaming_pb2.CollectorMessage],
        context: grpc.aio.ServicerContext,
    ) -> AsyncIterator[ecg_streaming_pb2.AggregatorMessage]:
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
                    ack = ecg_streaming_pb2.RegistrationAck(
                        accepted=True,
                        message=f"Collector {collector_id} registered successfully",
                        server_time_ms=int(time.time() * 1000),
                    )

                    yield ecg_streaming_pb2.AggregatorMessage(registration_ack=ack)

                elif msg_type == "ecg_batch":
                    # Handle ECG sample batch
                    batch = message.ecg_batch
                    device_id = batch.device_id

                    # Process each sample in the batch
                    for proto_sample in batch.samples:
                        await self._process_ecg_sample(device_id, proto_sample)

                    self._samples_received += len(batch.samples)

                    # Send sync status update if ready
                    if self.time_alignment.is_device_ready(device_id):
                        state = self.time_alignment._device_models.get(device_id)
                        if state and state.model:
                            sync_status = ecg_streaming_pb2.SyncStatusUpdate(
                                device_id=device_id,
                                sync_ready=True,
                                offset_s=state.model.offset,
                                offset_version=state.offset_version,
                                confidence=state.model.confidence,
                            )

                            yield ecg_streaming_pb2.AggregatorMessage(sync_status=sync_status)

                elif msg_type == "acc_batch":
                    # Handle accelerometer sample batch
                    batch = message.acc_batch
                    device_id = batch.device_id

                    # Process each sample in the batch
                    for proto_sample in batch.samples:
                        await self._process_acc_sample(device_id, proto_sample)

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

                    logger.debug(f"Status update from {device_id}: {status_str}")

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

                del self.collectors[collector_id]

    async def _process_ecg_sample(
        self, device_id: str, proto_sample: ecg_streaming_pb2.ECGSample
    ) -> None:
        """Process a single ECG sample.

        Args:
            device_id: Device identifier
            proto_sample: Protocol buffer ECG sample
        """
        # Convert proto sample to ECGSample
        sample = ECGSample(
            device_id=device_id,
            device_timestamp=proto_sample.device_timestamp_us,
            host_receive_time=proto_sample.host_receive_time_s,
            raw_value=proto_sample.raw_value,
            sample_rate=proto_sample.sample_rate,
        )

        # Add timestamp pair to time alignment service
        self.time_alignment.add_timestamp_pair(
            device_id=device_id,
            device_timestamp=sample.device_timestamp,
            host_receive_time=sample.host_receive_time,
        )

        # Synchronize timestamp
        synced = self.time_alignment.sync_timestamp(
            device_id=device_id, device_timestamp=sample.device_timestamp
        )

        # Only add to buffer if sync confidence is high enough
        if synced and synced.confidence >= 0.8:
            self.ecg_buffer.add_sample(
                device_id=device_id,
                global_time=synced.global_time,
                raw_value=sample.raw_value,
                confidence=synced.confidence,
            )

        # Store in database
        if self.database:
            confidence = synced.confidence if synced else 0.0
            global_time = synced.global_time if synced else sample.host_receive_time

            self.database.add_sample(
                device_id=device_id,
                global_time=global_time,
                device_timestamp=sample.device_timestamp,
                raw_value=sample.raw_value,
                confidence=confidence,
            )

    async def _process_acc_sample(
        self, device_id: str, proto_sample: ecg_streaming_pb2.AccelerometerSample
    ) -> None:
        """Process a single accelerometer sample.

        Args:
            device_id: Device identifier
            proto_sample: Protocol buffer accelerometer sample
        """
        # Convert proto sample to AccelerometerSample
        sample = AccelerometerSample(
            device_id=device_id,
            device_timestamp=proto_sample.device_timestamp_us,
            host_receive_time=proto_sample.host_receive_time_s,
            x=proto_sample.x,
            y=proto_sample.y,
            z=proto_sample.z,
        )

        # Add timestamp pair to time alignment service (reuse same service for both ECG and ACC)
        self.time_alignment.add_timestamp_pair(
            device_id=device_id,
            device_timestamp=sample.device_timestamp,
            host_receive_time=sample.host_receive_time,
        )

        # Synchronize timestamp
        synced = self.time_alignment.sync_timestamp(
            device_id=device_id, device_timestamp=sample.device_timestamp
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
            )

        # Store in database
        if self.database:
            confidence = synced.confidence if synced else 0.0
            global_time = synced.global_time if synced else sample.host_receive_time

            self.database.add_acc_sample(
                device_id=device_id,
                global_time=global_time,
                device_timestamp=sample.device_timestamp,
                x=sample.x,
                y=sample.y,
                z=sample.z,
                confidence=confidence,
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

    ecg_streaming_pb2_grpc.add_ECGStreamingServiceServicer_to_server(servicer, server)

    listen_addr = f"[::]:{port}"
    server.add_insecure_port(listen_addr)

    logger.info(f"Starting gRPC server on {listen_addr}")
    await server.start()

    try:
        await server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("Shutting down gRPC server...")
        await server.stop(grace=5)
