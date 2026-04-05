"""Session lifecycle application service."""

from ecg_common import DeviceStatus
from ecg_common.logging import get_logger

from ecg_aggregator.application.services.runtime_state import DeviceRegistry
from ecg_aggregator.domain.time import HostTimeSeconds
from ecg_aggregator.infrastructure.persistence.sqlite_database import ECGDatabase

logger = get_logger(__name__)


class SessionServiceError(RuntimeError):
    """Base exception for session lifecycle failures."""


class SessionAlreadyActiveError(SessionServiceError):
    """Raised when starting a session while one is already active."""


class NoActiveSessionError(SessionServiceError):
    """Raised when stopping a session while none is active."""


class SessionPersistenceError(SessionServiceError):
    """Raised when session state cannot be persisted or loaded."""


class SessionService:
    """Coordinate session lifecycle use cases."""

    def __init__(
        self,
        database: ECGDatabase | None = None,
        device_registry: DeviceRegistry | None = None,
    ) -> None:
        self.database = database
        self.device_registry = device_registry
        self._active_session_id: int | None = None
        self._active_session_start_time: HostTimeSeconds | None = None

    def start_session(self, notes: str | None = None) -> int:
        """Start a new recording session."""
        if self._active_session_id is not None:
            raise SessionAlreadyActiveError(
                f"Cannot start new session: session {self._active_session_id} is already active"
            )

        if not self.database:
            raise SessionPersistenceError("Cannot start session: no database configured")

        session_id = self.database.create_session(notes=notes)
        if session_id == -1:
            raise SessionPersistenceError("Failed to create session in database")

        session = self.database.get_session(session_id)
        if not session:
            raise SessionPersistenceError(f"Failed to fetch session {session_id} after creation")

        self._active_session_id = session_id
        self._active_session_start_time = HostTimeSeconds(session["start_time"])
        active_devices = [
            dev_id
            for dev_id, dev_status in (
                self.device_registry.device_statuses.items() if self.device_registry else []
            )
            if dev_status.status == DeviceStatus.STREAMING
        ]
        logger.info(
            "Started session %s with %d streaming devices",
            session_id,
            len(active_devices),
        )
        if active_devices:
            logger.info("  Streaming: %s", ", ".join(active_devices))
        return session_id

    def stop_session(self) -> int:
        """Stop the current recording session."""
        if self._active_session_id is None:
            raise NoActiveSessionError("Cannot stop session: no active session")

        if not self.database:
            raise SessionPersistenceError("Cannot stop session: no database configured")

        success = self.database.end_session(self._active_session_id)
        if not success:
            raise SessionPersistenceError(
                f"Failed to persist end of session {self._active_session_id}"
            )

        stopped_session_id = self._active_session_id
        session = self.database.get_session(stopped_session_id)
        self._active_session_id = None
        self._active_session_start_time = None

        if session:
            logger.info(
                "Stopped session %s: %.1fs, %s devices, %s ECG samples, %s ACC samples",
                stopped_session_id,
                session.get("duration_seconds", 0),
                session.get("device_count", 0),
                session.get("ecg_sample_count", 0),
                session.get("acc_sample_count", 0),
            )
        else:
            logger.info("Stopped recording session %s", stopped_session_id)

        return stopped_session_id

    def get_active_session_id(self) -> int | None:
        """Return the active session ID, if any."""
        return self._active_session_id

    def get_active_session_start_time(self) -> HostTimeSeconds | None:
        """Return the active session start time, if any."""
        return self._active_session_start_time
