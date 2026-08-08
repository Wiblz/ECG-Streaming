"""gRPC server for receiving ECG data from collectors."""

import asyncio
from collections.abc import AsyncIterator

import grpc
from ecg_common import DeviceStatus, DeviceStatusCode
from ecg_common.logging import get_logger
from ecg_common.proto import collector_aggregator_pb2, collector_aggregator_pb2_grpc

from ecg_aggregator.application.dto.ingest import (
    AccelerometerBatchInDTO,
    AccelerometerSampleInDTO,
    CollectorRegistrationDTO,
    DeviceStatusUpdateDTO,
    ECGBatchInDTO,
    ECGSampleInDTO,
)
from ecg_aggregator.application.services.ingest_service import IngestService
from ecg_aggregator.domain.time import DeviceTimestampUs, ReceiverClockUs, WallClockUs

logger = get_logger(__name__)


class ECGStreamingServicer(collector_aggregator_pb2_grpc.ECGStreamingServiceServicer):
    """gRPC servicer for ECG streaming."""

    def __init__(self, ingest_service: IngestService):
        self.ingest_service = ingest_service

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
        generation: int | None = None
        try:
            async for message in request_iterator:
                msg_type = message.WhichOneof("message")

                # Update last-seen timestamp on ANY message from collector
                if collector_id:
                    self.ingest_service.record_activity(collector_id)

                if msg_type == "registration":
                    (
                        collector_id,
                        device_ids,
                        generation,
                        registration_response,
                    ) = await self._handle_registration(message)
                    yield registration_response

                elif msg_type == "ecg_batch":
                    sync_response = await self._handle_ecg_batch(collector_id, message)
                    if sync_response is not None:
                        yield sync_response

                elif msg_type == "acc_batch":
                    await self._handle_acc_batch(collector_id, message)

                elif msg_type == "status_update":
                    await self._handle_status_update(collector_id, message)

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

        except asyncio.CancelledError:
            logger.info(f"Stream cancelled for collector {collector_id}")
            raise

        except Exception as e:
            logger.error(f"Error in stream for collector {collector_id}: {e}")
            await context.abort(grpc.StatusCode.INTERNAL, str(e))

        finally:
            if collector_id:
                logger.info(f"Collector {collector_id} disconnected")
                await self.ingest_service.disconnect_collector(collector_id, generation=generation)

    async def _handle_registration(
        self,
        message: collector_aggregator_pb2.CollectorMessage,
    ) -> tuple[str, list[str], int, collector_aggregator_pb2.AggregatorMessage]:
        """Handle collector registration and build the registration acknowledgement."""
        reg = message.registration
        collector_id = reg.collector_id
        device_ids = list(reg.device_ids)
        display_name = reg.display_name or collector_id

        logger.info(
            f"Collector {display_name} ({collector_id}) registered with {len(device_ids)} devices"
        )
        if device_ids:
            logger.info(f"  Devices: {', '.join(device_ids)}")

        ack_dto, generation = await self.ingest_service.register_collector(
            CollectorRegistrationDTO(
                collector_id=collector_id,
                display_name=display_name,
                device_ids=device_ids,
                version=reg.version,
                metadata=dict(reg.metadata),
                device_nicknames=dict(reg.device_nicknames),
            )
        )

        ack = collector_aggregator_pb2.RegistrationAck(
            accepted=ack_dto.accepted,
            message=ack_dto.message,
            server_time_ms=ack_dto.server_time_ms,
        )
        return (
            collector_id,
            device_ids,
            generation,
            collector_aggregator_pb2.AggregatorMessage(registration_ack=ack),
        )

    async def _handle_ecg_batch(
        self,
        collector_id: str | None,
        message: collector_aggregator_pb2.CollectorMessage,
    ) -> collector_aggregator_pb2.AggregatorMessage | None:
        """Handle an ECG batch and optionally return a sync-status response."""
        batch = message.ecg_batch
        sync_status_dto = await self.ingest_service.process_ecg_batch(
            collector_id=collector_id,
            batch=ECGBatchInDTO(
                device_id=batch.device_id,
                sample_rate=batch.sample_rate,
                wall_clock_us=WallClockUs(batch.wall_clock_us),
                samples=[
                    ECGSampleInDTO(
                        value=sample.value,
                        wall_clock_us=WallClockUs(sample.wall_clock_us),
                        polar_clock_us=DeviceTimestampUs(sample.polar_clock_us),
                        receiver_clock_us=ReceiverClockUs(sample.receiver_clock_us),
                        time_verified=sample.time_verified,
                    )
                    for sample in batch.samples
                ],
            ),
        )

        if sync_status_dto is None:
            return None

        return collector_aggregator_pb2.AggregatorMessage(
            sync_status=collector_aggregator_pb2.SyncStatusUpdate(
                device_id=sync_status_dto.device_id,
                sync_ready=sync_status_dto.sync_ready,
                offset_s=sync_status_dto.offset_s,
                offset_version=sync_status_dto.offset_version,
                confidence=sync_status_dto.confidence,
            )
        )

    async def _handle_acc_batch(
        self,
        collector_id: str | None,
        message: collector_aggregator_pb2.CollectorMessage,
    ) -> None:
        """Handle an accelerometer batch."""
        batch = message.acc_batch
        logger.debug(
            f"[FLOW] Received ACC batch from {batch.device_id}: {len(batch.samples)} samples"
        )

        await self.ingest_service.process_acc_batch(
            collector_id=collector_id,
            batch=AccelerometerBatchInDTO(
                device_id=batch.device_id,
                sample_rate=batch.sample_rate,
                wall_clock_us=WallClockUs(batch.wall_clock_us),
                samples=[
                    AccelerometerSampleInDTO(
                        x=sample.x,
                        y=sample.y,
                        z=sample.z,
                        wall_clock_us=WallClockUs(sample.wall_clock_us),
                        polar_clock_us=DeviceTimestampUs(sample.polar_clock_us),
                        receiver_clock_us=ReceiverClockUs(sample.receiver_clock_us),
                        time_verified=sample.time_verified,
                    )
                    for sample in batch.samples
                ],
            ),
        )

    async def _handle_status_update(
        self,
        collector_id: str | None,
        message: collector_aggregator_pb2.CollectorMessage,
    ) -> None:
        """Handle a device status update from a collector."""
        status = message.status_update
        device_id = status.device_id

        status_map = {
            DeviceStatusCode.UNKNOWN.value: DeviceStatus.UNKNOWN,
            DeviceStatusCode.DISCONNECTED.value: DeviceStatus.DISCONNECTED,
            DeviceStatusCode.CONNECTING.value: DeviceStatus.CONNECTING,
            DeviceStatusCode.CONNECTED.value: DeviceStatus.CONNECTED,
            DeviceStatusCode.STREAMING.value: DeviceStatus.STREAMING,
            DeviceStatusCode.ERROR.value: DeviceStatus.ERROR,
        }
        status_name = status_map.get(status.status, DeviceStatus.UNKNOWN)

        await self.ingest_service.update_device_status(
            collector_id=collector_id,
            status_update=DeviceStatusUpdateDTO(
                device_id=device_id,
                status=status_name,
                battery_level=status.battery_level if status.HasField("battery_level") else None,
                error_message=status.error_message if status.HasField("error_message") else None,
            ),
        )

        logger.debug(f"Status update from {device_id}: {status_name}")
