"""Device last_seen must track any contact, not just persisted samples."""

import time
from pathlib import Path

import pytest
from ecg_aggregator.application.dto.ingest import CollectorRegistrationDTO
from ecg_aggregator.application.services.ingest_service import IngestService
from ecg_aggregator.application.services.runtime_state import CollectorRegistry, DeviceRegistry
from ecg_aggregator.application.services.session_service import SessionService
from ecg_aggregator.infrastructure.persistence.sqlite_database import ECGDatabase
from ecg_aggregator.infrastructure.realtime.buffers import (
    AccelerometerDataBuffer,
    ECGDataBuffer,
)
from ecg_aggregator.sync.time_alignment import TimeAlignmentService


@pytest.fixture
def database(tmp_path: Path) -> ECGDatabase:
    db = ECGDatabase(db_path=tmp_path / "test.db")
    yield db
    db.close()


def _make_service(database: ECGDatabase | None) -> IngestService:
    device_registry = DeviceRegistry()
    return IngestService(
        time_alignment=TimeAlignmentService(),
        ecg_buffer=ECGDataBuffer(),
        acc_buffer=AccelerometerDataBuffer(),
        database=database,
        calibration_manager=None,
        event_bus=None,
        collector_registry=CollectorRegistry(),
        device_registry=device_registry,
        session_service=SessionService(device_registry=device_registry),
    )


def _registration(device_ids: list[str] | None = None) -> CollectorRegistrationDTO:
    return CollectorRegistrationDTO(
        collector_id="collector-1",
        display_name="Collector 1",
        device_ids=device_ids or ["device-a"],
        version="1.0.0",
        metadata={},
        device_nicknames={},
    )


def _db_last_seen(database: ECGDatabase, device_id: str) -> float | None:
    devices = {d["device_id"]: d for d in database.get_all_devices()}
    row = devices.get(device_id)
    return row["last_seen"] if row else None


def test_update_devices_last_seen_only_moves_forward(database: ECGDatabase) -> None:
    assert database.update_devices_last_seen({"device-a": 1000.0})
    assert _db_last_seen(database, "device-a") == 1000.0

    # A stale flush must not regress a newer value.
    assert database.update_devices_last_seen({"device-a": 500.0})
    assert _db_last_seen(database, "device-a") == 1000.0

    assert database.update_devices_last_seen({"device-a": 2000.0})
    assert _db_last_seen(database, "device-a") == 2000.0


async def test_registration_advances_last_seen(database: ECGDatabase) -> None:
    database.update_devices_last_seen({"device-a": 1000.0})

    service = _make_service(database)
    before = time.time()
    await service.register_collector(_registration())

    last_seen = _db_last_seen(database, "device-a")
    assert last_seen is not None and last_seen >= before


async def test_flush_persists_runtime_contact(database: ECGDatabase) -> None:
    service = _make_service(database)
    await service.register_collector(_registration())

    before = time.time()
    service.device_registry.mark_data_received(device_id="device-a", collector_id="collector-1")
    await service._flush_device_last_seen()

    last_seen = _db_last_seen(database, "device-a")
    assert last_seen is not None and last_seen >= before


async def test_disconnect_persists_final_contact(database: ECGDatabase) -> None:
    service = _make_service(database)
    _, generation = await service.register_collector(_registration())

    before = time.time()
    service.device_registry.mark_data_received(device_id="device-a", collector_id="collector-1")
    await service.disconnect_collector("collector-1", generation=generation)

    last_seen = _db_last_seen(database, "device-a")
    assert last_seen is not None and last_seen >= before
    assert "device-a" not in service._device_last_seen_persisted


def test_runtime_contact_wins_over_stale_db_value(database: ECGDatabase) -> None:
    from ecg_aggregator.application.services.device_query_service import DeviceQueryService
    from ecg_aggregator.domain.queries import SortOrder

    stale = time.time() - 3600.0
    database.update_devices_last_seen({"device-a": stale})

    device_registry = DeviceRegistry()
    device_registry.mark_data_received(device_id="device-a", collector_id="collector-1")

    query_service = DeviceQueryService(
        database=database,
        time_alignment=TimeAlignmentService(),
        collector_registry=CollectorRegistry(),
        device_registry=device_registry,
    )
    result = query_service.list_all_devices(
        limit=None,
        offset=0,
        search=None,
        sync_ready=None,
        show_simulated=True,
        status=None,
        collector_id=None,
        has_nickname=None,
        sort_by="last_seen",
        sort_order=SortOrder.DESC,
    )
    (device,) = result.items
    assert device.last_seen is not None
    assert device.last_seen > stale
