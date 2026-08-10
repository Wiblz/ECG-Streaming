"""Device query application service."""

from ecg_common import DeviceStatus

from ecg_aggregator.application.dto.query import (
    DeviceInfoDTO,
    DeviceStatusDTO,
    DeviceSummaryDTO,
    PaginatedResult,
    SyncInfoDTO,
)
from ecg_aggregator.application.services.runtime_state import CollectorRegistry, DeviceRegistry
from ecg_aggregator.domain.queries import DeviceListSortField, DeviceSummarySortField, SortOrder
from ecg_aggregator.domain.time import HostTimeSeconds
from ecg_aggregator.infrastructure.persistence.sqlite_database import ECGDatabase
from ecg_aggregator.sync.time_alignment import TimeAlignmentService, TimeModel


class DeviceQueryService:
    """Read-oriented device queries."""

    def __init__(
        self,
        *,
        database: ECGDatabase,
        time_alignment: TimeAlignmentService,
        collector_registry: CollectorRegistry,
        device_registry: DeviceRegistry,
    ) -> None:
        self.database = database
        self.time_alignment = time_alignment
        self.collector_registry = collector_registry
        self.device_registry = device_registry

    def list_device_summaries(
        self,
        *,
        limit: int | None,
        offset: int,
        search: str | None,
        sync_ready: bool | None,
        show_simulated: bool | None,
        sort_by: DeviceSummarySortField,
        sort_order: SortOrder,
    ) -> PaginatedResult[DeviceSummaryDTO]:
        """List synchronized device summaries."""
        devices: list[DeviceSummaryDTO] = []
        for device_id in self.time_alignment.get_all_models():
            sync_model = self.time_alignment.get_device_model(device_id)
            sync_info = self._build_sync_info(sync_model)
            devices.append(
                DeviceSummaryDTO(
                    device_id=device_id,
                    sync_ready=self.time_alignment.is_device_ready(device_id),
                    sync=sync_info,
                )
            )

        if search:
            search_normalized = search.lower()
            devices = [
                device for device in devices if search_normalized in device.device_id.lower()
            ]

        if sync_ready is not None:
            devices = [device for device in devices if device.sync_ready is sync_ready]
        if not show_simulated:
            devices = [device for device in devices if not device.is_simulated]

        reverse = sort_order is SortOrder.DESC
        if sort_by == "sync_ready":
            devices.sort(key=lambda d: (d.sync_ready, d.device_id), reverse=reverse)
        elif sort_by == "confidence":
            devices.sort(key=lambda d: (d.sync_confidence, d.device_id), reverse=reverse)
        elif sort_by == "sample_count":
            devices.sort(key=lambda d: (d.sync_sample_count, d.device_id), reverse=reverse)
        else:
            devices.sort(key=lambda d: d.device_id, reverse=reverse)

        total = len(devices)
        items = devices[offset:]
        if limit is not None:
            items = items[:limit]
        return PaginatedResult(items=items, total=total, limit=limit, offset=offset)

    def list_device_statuses(self) -> list[DeviceStatusDTO]:
        """Return current runtime status for all devices."""
        collector_names = {
            collector_id: collector.display_name
            for collector_id, collector in self.collector_registry.collectors.items()
        }
        return [
            DeviceStatusDTO(
                device_id=device_id,
                collector_id=status_info.collector_id,
                collector_name=collector_names.get(
                    status_info.collector_id, status_info.collector_id
                )
                if status_info.collector_id
                else None,
                status=status_info.status,
                last_update=status_info.last_update,
                battery_level=status_info.battery_level,
                error_message=status_info.error_message,
            )
            for device_id, status_info in self.device_registry.device_statuses.items()
        ]

    def list_all_devices(
        self,
        *,
        limit: int | None,
        offset: int,
        search: str | None,
        sync_ready: bool | None,
        show_simulated: bool | None,
        status: DeviceStatus | None,
        collector_id: str | None,
        has_nickname: bool | None,
        sort_by: DeviceListSortField,
        sort_order: SortOrder,
    ) -> PaginatedResult[DeviceInfoDTO]:
        """Return merged persisted and runtime device information."""
        db_devices = {device["device_id"]: device for device in self.database.get_all_devices()}
        sync_devices = {
            device_id: self.time_alignment.get_device_model(device_id)
            for device_id in self.time_alignment.get_all_models()
        }
        device_statuses = self.device_registry.device_statuses
        all_device_ids = (
            set(db_devices.keys()) | set(sync_devices.keys()) | set(device_statuses.keys())
        )

        devices: list[DeviceInfoDTO] = []
        for device_id in all_device_ids:
            first_seen: HostTimeSeconds | None = None
            last_seen: HostTimeSeconds | None = None
            total_samples = 0
            nickname: str | None = None
            sync_model = sync_devices.get(device_id)
            sync_info = self._build_sync_info(sync_model)
            collector_id_value: str | None = None
            status_value = DeviceStatus.DISCONNECTED
            last_update: HostTimeSeconds | None = None
            battery_level: int | None = None
            error_message: str | None = None

            if device_id in db_devices:
                db_device = db_devices[device_id]
                first_seen = HostTimeSeconds(db_device["first_seen"])
                last_seen = HostTimeSeconds(db_device["last_seen"])
                total_samples = db_device["total_samples"]
                nickname = db_device["nickname"]

            if device_id in device_statuses:
                status_info = device_statuses[device_id]
                collector_id_value = status_info.collector_id
                status_value = status_info.status
                last_update = status_info.last_update
                battery_level = status_info.battery_level
                error_message = status_info.error_message
                # Runtime contact is fresher than the throttled DB value while
                # the device is connected.
                if last_seen is None or status_info.last_contact > last_seen:
                    last_seen = status_info.last_contact

            devices.append(
                DeviceInfoDTO(
                    device_id=device_id,
                    first_seen=first_seen,
                    last_seen=last_seen,
                    total_samples=total_samples,
                    nickname=nickname,
                    sync_ready=self.time_alignment.is_device_ready(device_id),
                    sync=sync_info,
                    collector_id=collector_id_value,
                    status=status_value,
                    last_update=last_update,
                    battery_level=battery_level,
                    error_message=error_message,
                )
            )

        if search:
            search_normalized = search.lower()
            devices = [
                device
                for device in devices
                if search_normalized in device.device_id.lower()
                or search_normalized in device.normalized_nickname
            ]

        if sync_ready is not None:
            devices = [device for device in devices if device.sync_ready is sync_ready]
        if not show_simulated:
            devices = [device for device in devices if not device.is_simulated]
        if status is not None:
            devices = [device for device in devices if device.status == status]
        if collector_id is not None:
            devices = [device for device in devices if device.collector_id == collector_id]
        if has_nickname is not None:
            devices = [device for device in devices if device.has_nickname is has_nickname]

        reverse = sort_order is SortOrder.DESC
        if sort_by == "first_seen":
            devices.sort(key=lambda d: ((d.first_seen or 0), d.device_id), reverse=reverse)
        elif sort_by == "total_samples":
            devices.sort(key=lambda d: ((d.total_samples or 0), d.device_id), reverse=reverse)
        elif sort_by == "device_id":
            devices.sort(key=lambda d: d.device_id, reverse=reverse)
        elif sort_by == "nickname":
            devices.sort(key=lambda d: (d.normalized_nickname, d.device_id), reverse=reverse)
        elif sort_by == "status":
            devices.sort(key=lambda d: (d.status.value, d.device_id), reverse=reverse)
        elif sort_by == "last_update":
            devices.sort(key=lambda d: ((d.last_update or 0), d.device_id), reverse=reverse)
        else:
            devices.sort(key=lambda d: ((d.last_seen or 0), d.device_id), reverse=reverse)

        total = len(devices)
        items = devices[offset:]
        if limit is not None:
            items = items[:limit]
        return PaginatedResult(items=items, total=total, limit=limit, offset=offset)

    def update_device_nickname(self, device_id: str, nickname: str | None) -> bool:
        """Update a device nickname."""
        return self.database.update_device_nickname(device_id, nickname)

    @staticmethod
    def _build_sync_info(sync_model: TimeModel | None) -> SyncInfoDTO | None:
        if sync_model is None:
            return None
        return SyncInfoDTO(
            confidence=sync_model.confidence,
            drift_ppm=(sync_model.drift - 1.0) * 1_000_000,
            sample_count=sync_model.sample_count,
        )
