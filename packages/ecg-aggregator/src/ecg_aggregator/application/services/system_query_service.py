"""System/debug query application service."""

from collections.abc import Callable

from ecg_aggregator.application.dto.system import (
    DebugConnectionDTO,
    DebugConnectionsDTO,
    SystemStatsDTO,
)
from ecg_aggregator.application.services.ingest_service import IngestService
from ecg_aggregator.domain.realtime import BufferStatsSnapshot
from ecg_aggregator.infrastructure.realtime.buffers import (
    AccelerometerDataBuffer,
    ECGDataBuffer,
)
from ecg_aggregator.sync.time_alignment import TimeAlignmentService


class SystemQueryService:
    """Read-oriented system and debug queries."""

    def __init__(
        self,
        *,
        time_alignment: TimeAlignmentService,
        ecg_buffer: ECGDataBuffer,
        acc_buffer: AccelerometerDataBuffer,
        ingest_service: IngestService,
        list_ecg_connections: Callable[[], list[DebugConnectionDTO]],
        list_acc_connections: Callable[[], list[DebugConnectionDTO]],
    ) -> None:
        self.time_alignment = time_alignment
        self.ecg_buffer = ecg_buffer
        self.acc_buffer = acc_buffer
        self.ingest_service = ingest_service
        self._list_ecg_connections = list_ecg_connections
        self._list_acc_connections = list_acc_connections

    def get_stats(self) -> SystemStatsDTO:
        """Return aggregate system stats."""
        active_devices = self.ingest_service.get_active_device_count()
        ecg_stats = {**self.ecg_buffer.get_stats(), "device_count": active_devices}
        acc_stats = {**self.acc_buffer.get_stats(), "device_count": active_devices}
        ecg_connections = self._list_ecg_connections()
        acc_connections = self._list_acc_connections()

        return SystemStatsDTO(
            sync=self.time_alignment.get_sync_stats(),
            ingest=self.ingest_service.get_stats(),
            ecg_websocket_connections=len(ecg_connections),
            acc_websocket_connections=len(acc_connections),
            ecg_buffer=BufferStatsSnapshot.model_validate(ecg_stats),
            acc_buffer=BufferStatsSnapshot.model_validate(acc_stats),
        )

    def get_debug_connections(self) -> DebugConnectionsDTO:
        """Return detailed websocket connection info."""
        ecg_connections = self._list_ecg_connections()
        acc_connections = self._list_acc_connections()
        return DebugConnectionsDTO(
            ecg_count=len(ecg_connections),
            acc_count=len(acc_connections),
            ecg_connections=ecg_connections,
            acc_connections=acc_connections,
        )
