"""Ingest orchestration application service."""

import asyncio
import contextlib
import math
import time

from ecg_common import DeviceStatus
from ecg_common.logging import get_logger

from ecg_aggregator.application.dto.ingest import (
    AccelerometerBatchInDTO,
    AccelerometerSampleInDTO,
    CollectorRegistrationDTO,
    DeviceStatusUpdateDTO,
    ECGBatchInDTO,
    ECGSampleInDTO,
    RegistrationAckDTO,
    SyncStatusDTO,
)
from ecg_aggregator.application.dto.system import IngestStats
from ecg_aggregator.application.ports.event_bus import DomainEventBus
from ecg_aggregator.application.services.runtime_state import CollectorRegistry, DeviceRegistry
from ecg_aggregator.application.services.sample_batch_writer import (
    AccBatchRow,
    ECGBatchRow,
    SampleBatchWriter,
)
from ecg_aggregator.application.services.session_service import SessionService
from ecg_aggregator.domain.events import (
    AlignmentUpdated,
    BufferStatsUpdated,
    CollectorDisconnected,
    CollectorRegistered,
    CollectorUpdated,
    DeviceUpdated,
    TapDetected,
)
from ecg_aggregator.domain.realtime import BufferStatsSnapshot
from ecg_aggregator.domain.time import DeviceTimestampUs, HostTimeSeconds, Seconds
from ecg_aggregator.infrastructure.persistence.sqlite_database import ECGDatabase
from ecg_aggregator.infrastructure.realtime.buffers import (
    AccelerometerDataBuffer,
    ECGDataBuffer,
)
from ecg_aggregator.sync.calibration_manager import CalibrationManager
from ecg_aggregator.sync.spike_detector import AccSample
from ecg_aggregator.sync.time_alignment import TimeAlignmentService

logger = get_logger(__name__)
ACTIVE_DEVICE_WINDOW_S = Seconds(30.0)


class IngestService:
    """Coordinate the live collector ingest pipeline.

    This service is the application-layer entry point for collector traffic after
    the gRPC adapter has translated protobuf messages into typed DTOs.

    Responsibilities:
    - register collectors and initialize their runtime state
    - update collector heartbeats and device runtime status
    - feed raw device/host timestamp pairs into the time-alignment service
    - transform synchronized samples into recent in-memory realtime buffers
    - enqueue session-bound samples for batched persistence
    - trigger calibration/spike-detection processing for accelerometer data
    - publish domain events describing collector, device, and calibration changes

    This service intentionally does not own transport concerns. It does not parse
    protobufs, manage HTTP/WebSocket connections, or expose storage/query APIs.
    Those concerns stay in the delivery adapters and persistence layer.
    """

    def __init__(
        self,
        *,
        time_alignment: TimeAlignmentService,
        ecg_buffer: ECGDataBuffer,
        acc_buffer: AccelerometerDataBuffer,
        database: ECGDatabase | None,
        calibration_manager: CalibrationManager | None,
        event_bus: DomainEventBus | None,
        collector_registry: CollectorRegistry,
        device_registry: DeviceRegistry,
        session_service: SessionService,
    ) -> None:
        """Initialize the ingest service."""
        self.time_alignment = time_alignment
        self.ecg_buffer = ecg_buffer
        self.acc_buffer = acc_buffer
        self.database = database
        self.calibration_manager = calibration_manager
        self.event_bus = event_bus
        self.collector_registry = collector_registry
        self.device_registry = device_registry
        self.session_service = session_service
        self._sample_batch_writer = SampleBatchWriter(self.database)

        self._samples_received = 0
        self._acc_samples_received = 0
        self._last_frame_ts: dict[tuple[str, str], int] = {}
        self._sync_ready_logged: dict[str, int] = {}
        self._stats_task: asyncio.Task[None] | None = None

    def start_flush_task(self) -> None:
        """Start periodic batch flushing."""
        self._sample_batch_writer.start()

    async def stop_flush_task(self) -> None:
        """Stop periodic batch flushing."""
        await self._sample_batch_writer.stop()

    def start_stats_task(self, interval_s: float = 1.0) -> None:
        """Start periodic buffer stats publishing."""
        if self._stats_task is None or self._stats_task.done():
            self._stats_task = asyncio.create_task(self._publish_buffer_stats(interval_s))

    async def stop_stats_task(self) -> None:
        """Stop periodic buffer stats publishing."""
        if self._stats_task and not self._stats_task.done():
            self._stats_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._stats_task

    async def _publish_buffer_stats(self, interval_s: float) -> None:
        """Periodically publish a BufferStatsUpdated domain event."""
        while True:
            try:
                await asyncio.sleep(interval_s)
                if not self.event_bus:
                    continue
                active_devices = self.get_active_device_count()
                ecg_stats = self.ecg_buffer.get_stats(consume_rate=True)
                acc_stats = self.acc_buffer.get_stats(consume_rate=True)
                ecg_stats = {**ecg_stats, "device_count": active_devices}
                acc_stats = {**acc_stats, "device_count": active_devices}
                await self.event_bus.publish(
                    BufferStatsUpdated(
                        ecg_stats=BufferStatsSnapshot.model_validate(ecg_stats),
                        acc_stats=BufferStatsSnapshot.model_validate(acc_stats),
                        active_device_count=active_devices,
                    )
                )
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Error publishing buffer stats: %s", exc)

    def record_activity(self, collector_id: str) -> None:
        """Update the last-seen timestamp for a connected collector."""
        self.collector_registry.record_activity(collector_id)

    async def register_collector(
        self, registration: CollectorRegistrationDTO
    ) -> RegistrationAckDTO:
        """Register a collector and initialize its runtime state."""
        self.collector_registry.register(
            collector_id=registration.collector_id,
            display_name=registration.display_name,
            device_ids=registration.device_ids,
            version=registration.version,
            metadata=registration.metadata,
        )

        if self.event_bus:
            await self.event_bus.publish(
                CollectorRegistered(
                    collector_id=registration.collector_id,
                    display_name=registration.display_name,
                    device_ids=tuple(registration.device_ids),
                )
            )

        if self.database:
            self.database.upsert_collector(
                collector_id=registration.collector_id,
                display_name=registration.display_name,
                version=registration.version,
                metadata=registration.metadata,
            )

            for device_id in registration.device_ids:
                self.database.ensure_device(device_id)
                self.database.upsert_device_collector_mapping(
                    device_id=device_id,
                    collector_id=registration.collector_id,
                )

            for device_id, nickname in registration.device_nicknames.items():
                if nickname:
                    self.database.update_device_nickname(device_id, nickname)
                    logger.info(
                        "Set nickname for %s to '%s' from collector config",
                        device_id,
                        nickname,
                    )

        for device_id in registration.device_ids:
            self.device_registry.ensure_device(
                device_id=device_id,
                collector_id=registration.collector_id,
                status=DeviceStatus.DISCONNECTED,
            )

        return RegistrationAckDTO(
            accepted=True,
            message=f"Collector {registration.collector_id} registered successfully",
            server_time_ms=int(time.time() * 1000),
        )

    async def process_ecg_batch(
        self,
        *,
        collector_id: str | None,
        batch: ECGBatchInDTO,
    ) -> SyncStatusDTO | None:
        """Process an ECG sample batch."""
        process_start = time.time()
        wall_clock_s = self._prepare_batch_sync(
            device_id=batch.device_id,
            sample_rate=batch.sample_rate,
            wall_clock_us=batch.wall_clock_us,
            samples=batch.samples,
            sensor_type="ecg",
            sensor_label="ECG",
        )
        if wall_clock_s is None:
            return None

        samples_added = 0
        samples_low_confidence = 0
        samples_no_sync = 0
        for sample in batch.samples:
            synced = self.time_alignment.sync_timestamp(
                device_id=batch.device_id,
                device_timestamp=DeviceTimestampUs(sample.polar_clock_us),
            )

            if not synced:
                samples_no_sync += 1
                continue

            if synced.confidence >= 0.8:
                self.ecg_buffer.add_sample(
                    device_id=batch.device_id,
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

            if self.database and self.session_service.get_active_session_id() is not None:
                confidence = synced.confidence if synced else 0.0
                global_time = synced.global_time if synced else wall_clock_s
                session_id = self._resolve_session_id(global_time)

                self._sample_batch_writer.add_ecg_sample(
                    ECGBatchRow(
                        device_id=batch.device_id,
                        global_time=global_time,
                        device_timestamp=sample.polar_clock_us,
                        raw_value=sample.value,
                        confidence=confidence,
                        session_id=session_id,
                        wall_clock_us=sample.wall_clock_us,
                        receiver_clock_us=sample.receiver_clock_us,
                        time_verified=sample.time_verified,
                    )
                )

        await self._finalize_batch(
            collector_id=collector_id,
            device_id=batch.device_id,
            sample_count=len(batch.samples),
            update_collector_health=True,
            samples_received_attr="_samples_received",
        )

        process_duration = (time.time() - process_start) * 1000
        if samples_no_sync > 0 or samples_low_confidence > 0:
            logger.warning(
                "[FLOW] ECG batch from %s: %d received, %d added, %d no sync, %d low confidence",
                batch.device_id,
                len(batch.samples),
                samples_added,
                samples_no_sync,
                samples_low_confidence,
            )
        elif process_duration > 50:
            logger.warning(
                "[FLOW] Slow ECG batch processing for %s: %.1fms for %d samples",
                batch.device_id,
                process_duration,
                len(batch.samples),
            )

        return self._build_sync_status(batch.device_id)

    async def process_acc_batch(
        self,
        *,
        collector_id: str | None,
        batch: AccelerometerBatchInDTO,
    ) -> None:
        """Process an accelerometer sample batch."""
        process_start = time.time()
        wall_clock_s = self._prepare_batch_sync(
            device_id=batch.device_id,
            sample_rate=batch.sample_rate,
            wall_clock_us=batch.wall_clock_us,
            samples=batch.samples,
            sensor_type="acc",
            sensor_label="ACC",
        )
        if wall_clock_s is None:
            return

        for sample in batch.samples:
            synced = self.time_alignment.sync_timestamp(
                device_id=batch.device_id,
                device_timestamp=DeviceTimestampUs(sample.polar_clock_us),
            )

            if synced and synced.confidence >= 0.8:
                self.acc_buffer.add_sample(
                    device_id=batch.device_id,
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

            if self.calibration_manager and synced:
                magnitude = math.sqrt(sample.x**2 + sample.y**2 + sample.z**2)
                acc_sample = AccSample(
                    device_id=batch.device_id,
                    global_time=synced.global_time,
                    device_timestamp=sample.polar_clock_us,
                    x=sample.x,
                    y=sample.y,
                    z=sample.z,
                    magnitude=magnitude,
                )
                tap_event, alignment = self.calibration_manager.process_acc_sample(acc_sample)

                if tap_event and self.event_bus:
                    await self.event_bus.publish(
                        TapDetected(
                            device_id=tap_event.device_id,
                            tap_timestamp=tap_event.tap_timestamp,
                            magnitude=tap_event.magnitude,
                            confidence=tap_event.confidence,
                        )
                    )

                if alignment and self.event_bus:
                    await self.event_bus.publish(
                        AlignmentUpdated(
                            device_id=alignment.device_id,
                            status=alignment.status,
                            confidence=alignment.confidence,
                            offset=alignment.time_offset,
                            tap_count=alignment.tap_count,
                            mean_error=alignment.mean_error,
                            std_error=alignment.std_error,
                        )
                    )

            if self.database and self.session_service.get_active_session_id() is not None:
                confidence = synced.confidence if synced else 0.0
                global_time = synced.global_time if synced else wall_clock_s
                session_id = self._resolve_session_id(global_time)

                self._sample_batch_writer.add_acc_sample(
                    AccBatchRow(
                        device_id=batch.device_id,
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
                )

        await self._finalize_batch(
            collector_id=collector_id,
            device_id=batch.device_id,
            sample_count=len(batch.samples),
            update_collector_health=False,
            samples_received_attr="_acc_samples_received",
        )

        process_duration = (time.time() - process_start) * 1000
        if process_duration > 50:
            logger.warning(
                "[FLOW] Slow ACC batch processing for %s: %.1fms for %d samples",
                batch.device_id,
                process_duration,
                len(batch.samples),
            )

    async def update_device_status(
        self,
        *,
        collector_id: str | None,
        status_update: DeviceStatusUpdateDTO,
    ) -> None:
        """Update runtime device status from a collector."""
        self.device_registry.update_status(
            device_id=status_update.device_id,
            collector_id=collector_id or "",
            status=status_update.status,
            battery_level=status_update.battery_level,
            error_message=status_update.error_message,
        )

        if self.event_bus and collector_id:
            await self.event_bus.publish(
                DeviceUpdated(
                    device_id=status_update.device_id,
                    collector_id=collector_id,
                    status=status_update.status,
                    battery_level=status_update.battery_level,
                    error_message=status_update.error_message,
                )
            )

    async def disconnect_collector(self, collector_id: str) -> None:
        """Handle collector disconnect cleanup. No-op if collector was never registered."""
        if collector_id not in self.collector_registry.collectors:
            return
        for device_id in self.device_registry.disconnect_collector_devices(collector_id):
            self._clear_device_stream_state(device_id)
            if self.event_bus:
                await self.event_bus.publish(
                    DeviceUpdated(
                        device_id=device_id,
                        collector_id=collector_id,
                        status=DeviceStatus.DISCONNECTED,
                    )
                )

        if self.event_bus:
            await self.event_bus.publish(CollectorDisconnected(collector_id=collector_id))
        self.collector_registry.remove(collector_id)

    def get_active_device_count(self, active_window_s: Seconds = ACTIVE_DEVICE_WINDOW_S) -> int:
        """Get total number of active devices across all collectors."""
        return self.device_registry.count_active_devices(active_window_s)

    def get_stats(self) -> IngestStats:
        """Get ingest-side statistics."""
        return {
            "collectors_connected": len(self.collector_registry.collectors),
            "collectors": list(self.collector_registry.collectors.keys()),
            "samples_received": self._samples_received,
            "acc_samples_received": self._acc_samples_received,
            "active_session_id": self.session_service.get_active_session_id(),
        }

    async def _publish_collector_health(self, collector_id: str) -> None:
        self._update_active_devices_count(collector_id)
        if not self.event_bus:
            return

        collector = self.collector_registry.collectors.get(collector_id)
        if collector:
            await self.event_bus.publish(
                CollectorUpdated(
                    collector_id=collector_id,
                    display_name=collector.display_name,
                    active_devices=collector.active_devices,
                    last_heartbeat=collector.last_seen,
                )
            )

    def _update_active_devices_count(self, collector_id: str) -> None:
        if collector_id not in self.collector_registry.collectors:
            return
        active_count = self.device_registry.count_active_devices_for_collector(collector_id)
        self.collector_registry.set_active_devices(collector_id, active_count)

    def _clear_device_stream_state(self, device_id: str) -> None:
        """Drop per-device ingest bookkeeping once the device disconnects."""
        self._sync_ready_logged.pop(device_id, None)
        self._last_frame_ts.pop((device_id, "ecg"), None)
        self._last_frame_ts.pop((device_id, "acc"), None)

    def _prepare_batch_sync(
        self,
        *,
        device_id: str,
        sample_rate: int,
        wall_clock_us: int,
        samples: list[ECGSampleInDTO] | list[AccelerometerSampleInDTO],
        sensor_type: str,
        sensor_label: str,
    ) -> HostTimeSeconds | None:
        """Run shared per-batch timestamp preparation and gap detection."""
        if not samples:
            return None

        last_sample = samples[-1]
        last_key = (device_id, sensor_type)
        prev_ts = self._last_frame_ts.get(last_key)
        if prev_ts is not None:
            sample_count = len(samples)
            expected_span_us = (
                int((sample_count - 1) * 1_000_000 / sample_rate)
                if sample_count > 1 and sample_rate > 0
                else 0
            )
            delta_us = last_sample.polar_clock_us - prev_ts
            gap_threshold_us = max(500_000, expected_span_us * 2)
            if delta_us > gap_threshold_us:
                logger.warning(
                    "Aggregator gap detected %s %s: delta_us=%d expected_span_us=%d samples=%d",
                    device_id,
                    sensor_label,
                    delta_us,
                    expected_span_us,
                    sample_count,
                )
        self._last_frame_ts[last_key] = last_sample.polar_clock_us
        wall_clock_s = HostTimeSeconds(wall_clock_us / 1_000_000.0)

        self.time_alignment.add_timestamp_pair(
            device_id=device_id,
            device_timestamp=DeviceTimestampUs(last_sample.polar_clock_us),
            host_receive_time=wall_clock_s,
            sensor_type=sensor_type,
        )
        return wall_clock_s

    def _resolve_session_id(self, global_time: float) -> int | None:
        """Resolve the active session for a sample timestamp, if any."""
        start_time = self.session_service.get_active_session_start_time()
        if start_time is None or global_time < start_time:
            return None
        return self.session_service.get_active_session_id()

    async def _finalize_batch(
        self,
        *,
        collector_id: str | None,
        device_id: str,
        sample_count: int,
        update_collector_health: bool,
        samples_received_attr: str,
    ) -> None:
        """Run shared post-batch persistence and runtime bookkeeping."""
        await self._sample_batch_writer.flush()
        setattr(self, samples_received_attr, getattr(self, samples_received_attr) + sample_count)

        if collector_id:
            self.collector_registry.add_samples_sent(collector_id, sample_count)

        self.device_registry.mark_data_received(
            device_id=device_id,
            collector_id=collector_id or "",
        )

        if not collector_id:
            return

        if update_collector_health:
            await self._publish_collector_health(collector_id)
        else:
            self._update_active_devices_count(collector_id)

    def _build_sync_status(self, device_id: str) -> SyncStatusDTO | None:
        if not self.time_alignment.is_device_ready(device_id):
            return None

        model = self.time_alignment.get_device_model(device_id)
        offset_version = self.time_alignment.get_offset_version(device_id)
        if model is None or offset_version is None:
            return None

        last_version = self._sync_ready_logged.get(device_id)
        if last_version != offset_version:
            self._sync_ready_logged[device_id] = offset_version
            logger.info(
                "Time sync ready for %s: offset=%.3fs, confidence=%.2f",
                device_id,
                model.offset,
                model.confidence,
            )

        return SyncStatusDTO(
            device_id=device_id,
            sync_ready=True,
            offset_s=model.offset,
            offset_version=offset_version,
            confidence=model.confidence,
        )
