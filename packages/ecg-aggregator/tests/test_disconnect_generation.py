"""Stale-stream disconnects must not tear down a superseding registration."""

from ecg_aggregator.application.dto.ingest import CollectorRegistrationDTO
from ecg_aggregator.application.services.ingest_service import IngestService
from ecg_aggregator.application.services.runtime_state import CollectorRegistry, DeviceRegistry
from ecg_aggregator.application.services.session_service import SessionService
from ecg_aggregator.infrastructure.realtime.buffers import (
    AccelerometerDataBuffer,
    ECGDataBuffer,
)
from ecg_aggregator.sync.time_alignment import TimeAlignmentService
from ecg_common import DeviceStatus


def _make_service() -> IngestService:
    device_registry = DeviceRegistry()
    return IngestService(
        time_alignment=TimeAlignmentService(),
        ecg_buffer=ECGDataBuffer(),
        acc_buffer=AccelerometerDataBuffer(),
        database=None,
        calibration_manager=None,
        event_bus=None,
        collector_registry=CollectorRegistry(),
        device_registry=device_registry,
        session_service=SessionService(device_registry=device_registry),
    )


def _registration() -> CollectorRegistrationDTO:
    return CollectorRegistrationDTO(
        collector_id="collector-1",
        display_name="Collector 1",
        device_ids=["device-a"],
        version="1.0.0",
        metadata={},
        device_nicknames={},
    )


async def test_stale_stream_disconnect_is_noop() -> None:
    service = _make_service()

    _, old_generation = await service.register_collector(_registration())
    _, new_generation = await service.register_collector(_registration())
    assert new_generation > old_generation
    assert list(service.collector_registry.collectors) == ["collector-1"]

    await service.disconnect_collector("collector-1", generation=old_generation)

    assert "collector-1" in service.collector_registry.collectors
    assert service.collector_registry.collectors["collector-1"].generation == new_generation
    assert "device-a" in service.device_registry.device_statuses


async def test_owning_stream_disconnect_tears_down() -> None:
    service = _make_service()

    _, generation = await service.register_collector(_registration())
    await service.disconnect_collector("collector-1", generation=generation)

    assert "collector-1" not in service.collector_registry.collectors
    assert "device-a" not in service.device_registry.device_statuses


async def test_reregistration_preserves_device_status() -> None:
    service = _make_service()

    await service.register_collector(_registration())
    service.device_registry.update_status(
        device_id="device-a",
        collector_id="collector-1",
        status=DeviceStatus.STREAMING,
        battery_level=80,
        error_message=None,
    )

    await service.register_collector(_registration())

    device = service.device_registry.device_statuses["device-a"]
    assert device.status == DeviceStatus.STREAMING
    assert device.battery_level == 80
