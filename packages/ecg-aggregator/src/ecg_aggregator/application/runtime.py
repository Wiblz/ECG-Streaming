"""Application runtime container for API wiring."""

from dataclasses import dataclass

from ecg_aggregator.application.services.buffer_query_service import BufferQueryService
from ecg_aggregator.application.services.calibration_service import CalibrationService
from ecg_aggregator.application.services.collector_query_service import CollectorQueryService
from ecg_aggregator.application.services.device_query_service import DeviceQueryService
from ecg_aggregator.application.services.ingest_service import IngestService
from ecg_aggregator.application.services.session_query_service import SessionQueryService
from ecg_aggregator.application.services.session_service import SessionService
from ecg_aggregator.application.services.system_query_service import SystemQueryService


@dataclass(frozen=True)
class ApplicationRuntime:
    """Shared runtime dependencies exposed to delivery adapters."""

    ingest_service: IngestService
    session_service: SessionService
    session_query_service: SessionQueryService
    device_query_service: DeviceQueryService
    buffer_query_service: BufferQueryService
    collector_query_service: CollectorQueryService
    system_query_service: SystemQueryService
    calibration_service: CalibrationService
