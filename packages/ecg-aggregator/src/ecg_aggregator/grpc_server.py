"""gRPC server for receiving ECG data from collectors."""

import asyncio
import time
from collections.abc import AsyncIterator

import grpc
from ecg_common.logging import get_logger
from ecg_common.models import ECGSample
from ecg_common.proto import ecg_streaming_pb2, ecg_streaming_pb2_grpc

from ecg_aggregator.api.data_buffer import ECGDataBuffer
from ecg_aggregator.storage.persistence import ECGDatabase
from ecg_aggregator.sync.time_alignment import TimeAlignmentService

logger = get_logger(__name__)


class ECGStreamingServicer(ecg_streaming_pb2_grpc.ECGStreamingServiceServicer):
    """gRPC servicer for ECG streaming."""

    def __init__(
        self,
        time_alignment: TimeAlignmentService,
        data_buffer: ECGDataBuffer,
        database: ECGDatabase | None = None,
    ):
        """Initialize the servicer.

        Args:
            time_alignment: Time alignment service
            data_buffer: Data buffer for recent samples
            database: Optional database for persistence
        """
        self.time_alignment = time_alignment
        self.data_buffer = data_buffer
        self.database = database

        # Track connected collectors
        self.collectors: dict[str, dict] = {}  # collector_id -> metadata

        # Statistics
        self._samples_received = 0

    async def StreamECG(
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

                    logger.info(
                        f"Collector {collector_id} registered with {len(device_ids)} devices: "
                        f"{', '.join(device_ids)}"
                    )

                    self.collectors[collector_id] = {
                        "device_ids": device_ids,
                        "version": reg.version,
                        "metadata": dict(reg.metadata),
                        "connected_at": time.time(),
                    }

                    # Send registration acknowledgment
                    ack = ecg_streaming_pb2.RegistrationAck(
                        accepted=True,
                        message=f"Collector {collector_id} registered successfully",
                        server_time_ms=int(time.time() * 1000),
                    )

                    yield ecg_streaming_pb2.AggregatorMessage(registration_ack=ack)

                elif msg_type == "sample_batch":
                    # Handle ECG sample batch
                    batch = message.sample_batch
                    device_id = batch.device_id

                    # Process each sample in the batch
                    for proto_sample in batch.samples:
                        await self._process_sample(device_id, proto_sample)

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

                elif msg_type == "status_update":
                    # Handle device status update
                    status = message.status_update
                    logger.debug(f"Status update from {status.device_id}: {status.status}")

                elif msg_type == "heartbeat":
                    # Handle heartbeat
                    hb = message.heartbeat
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
                del self.collectors[collector_id]

    async def _process_sample(
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
            self.data_buffer.add_sample(
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

    def get_stats(self) -> dict:
        """Get server statistics.

        Returns:
            Dictionary containing server statistics
        """
        return {
            "collectors_connected": len(self.collectors),
            "collectors": list(self.collectors.keys()),
            "samples_received": self._samples_received,
        }


async def serve(
    time_alignment: TimeAlignmentService,
    data_buffer: ECGDataBuffer,
    database: ECGDatabase | None = None,
    port: int = 50051,
) -> None:
    """Start the gRPC server.

    Args:
        time_alignment: Time alignment service
        data_buffer: Data buffer
        database: Optional database
        port: Server port
    """
    server = grpc.aio.server()

    servicer = ECGStreamingServicer(
        time_alignment=time_alignment,
        data_buffer=data_buffer,
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
