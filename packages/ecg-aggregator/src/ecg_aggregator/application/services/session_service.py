"""Session lifecycle application service."""

import asyncio
from collections.abc import Awaitable, Callable

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
        self._flush_pending_samples: Callable[[], Awaitable[None]] | None = None

    def set_flush_pending_samples(self, flush: Callable[[], Awaitable[None]]) -> None:
        """Register a hook that flushes buffered samples to the database."""
        self._flush_pending_samples = flush

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

    async def stop_session(self) -> int:
        """Stop the current recording session."""
        if self._active_session_id is None:
            raise NoActiveSessionError("Cannot stop session: no active session")

        if not self.database:
            raise SessionPersistenceError("Cannot stop session: no database configured")

        # Deactivate before flushing so ingest stops tagging new samples, and
        # flush before end_session so every tagged row is in the database when
        # end_session prunes out-of-range rows and freezes the session counts.
        stopped_session_id = self._active_session_id
        stopped_start_time = self._active_session_start_time
        self._active_session_id = None
        self._active_session_start_time = None

        loop = asyncio.get_running_loop()
        try:
            if self._flush_pending_samples is not None:
                await self._flush_pending_samples()
            success = await loop.run_in_executor(
                None, self.database.end_session, stopped_session_id
            )
        except Exception:
            self._active_session_id = stopped_session_id
            self._active_session_start_time = stopped_start_time
            raise
        if not success:
            self._active_session_id = stopped_session_id
            self._active_session_start_time = stopped_start_time
            raise SessionPersistenceError(f"Failed to persist end of session {stopped_session_id}")

        session = await loop.run_in_executor(None, self.database.get_session, stopped_session_id)

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
