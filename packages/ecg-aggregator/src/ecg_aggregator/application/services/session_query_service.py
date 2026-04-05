"""Session query application service."""

from pathlib import Path

from ecg_aggregator.application.dto.query import (
    AccelerometerSessionSampleDTO,
    ECGSessionSampleDTO,
    GroupedSamplesResult,
    PaginatedResult,
    SessionInfoDTO,
)
from ecg_aggregator.application.utils import group_samples_by_device
from ecg_aggregator.domain.queries import SessionSortField, SortOrder
from ecg_aggregator.infrastructure.persistence.sqlite_database import ECGDatabase


class SessionQueryService:
    """Read-oriented session queries."""

    def __init__(self, *, database: ECGDatabase) -> None:
        self.database = database

    def get_session(self, session_id: int) -> SessionInfoDTO | None:
        """Fetch a single session."""
        session = self.database.get_session(session_id)
        return SessionInfoDTO.model_validate(session) if session else None

    def list_sessions(
        self,
        *,
        limit: int | None,
        offset: int,
        search: str | None,
        active: bool | None,
        has_notes: bool | None,
        device_id: str | None,
        sort_by: SessionSortField,
        sort_order: SortOrder,
    ) -> PaginatedResult[SessionInfoDTO]:
        """Fetch a paginated session list."""
        sessions = self.database.get_sessions(
            limit=limit,
            offset=offset,
            search=search,
            active=active,
            has_notes=has_notes,
            device_id=device_id,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        items = [SessionInfoDTO.model_validate(session) for session in sessions]
        total = self.database.count_sessions(
            search=search,
            active=active,
            has_notes=has_notes,
            device_id=device_id,
        )
        return PaginatedResult(items=items, total=total, limit=limit, offset=offset)

    def get_ecg_samples(
        self,
        *,
        session_id: int,
        device_id: str | None,
        start_time: float | None,
        end_time: float | None,
        limit: int | None,
        offset: int,
    ) -> GroupedSamplesResult[ECGSessionSampleDTO]:
        """Fetch grouped ECG samples for a session."""
        samples = self.database.get_session_samples(
            session_id=session_id,
            device_id=device_id,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            offset=offset,
        )
        return GroupedSamplesResult(
            session_id=session_id,
            devices=group_samples_by_device(samples, ECGSessionSampleDTO),
            count=len(samples),
        )

    def get_accelerometer_samples(
        self,
        *,
        session_id: int,
        device_id: str | None,
        start_time: float | None,
        end_time: float | None,
        limit: int | None,
        offset: int,
    ) -> GroupedSamplesResult[AccelerometerSessionSampleDTO]:
        """Fetch grouped accelerometer samples for a session."""
        samples = self.database.get_session_accelerometer_samples(
            session_id=session_id,
            device_id=device_id,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            offset=offset,
        )
        return GroupedSamplesResult(
            session_id=session_id,
            devices=group_samples_by_device(samples, AccelerometerSessionSampleDTO),
            count=len(samples),
        )

    def delete_session(self, session_id: int) -> bool:
        """Delete a session."""
        return self.database.delete_session(session_id)

    def export_session_to_csv(self, session_id: int, output_path: Path) -> bool:
        """Export a session to CSV."""
        return self.database.export_session_to_csv(session_id, output_path)

    def import_session_from_csv(self, input_path: Path) -> int | None:
        """Import a session from CSV."""
        return self.database.import_session_from_csv(input_path)
