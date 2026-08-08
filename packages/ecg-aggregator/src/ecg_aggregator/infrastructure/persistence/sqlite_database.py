"""SQLite database connection management and unified facade."""

import sqlite3
from pathlib import Path
from threading import RLock

from ecg_common.logging import get_logger
from yoyo import get_backend, read_migrations
from yoyo.exceptions import LockTimeout

from ecg_aggregator.domain.queries import SessionSortField, SortOrder
from ecg_aggregator.domain.time import (
    DeviceTimestampUs,
    GlobalTimeSeconds,
    ReceiverClockUs,
    WallClockUs,
)
from ecg_aggregator.infrastructure.persistence.alignment_repository import AlignmentRepository
from ecg_aggregator.infrastructure.persistence.batch_rows import AccBatchRow, ECGBatchRow
from ecg_aggregator.infrastructure.persistence.device_repository import DeviceRepository
from ecg_aggregator.infrastructure.persistence.sample_repository import SampleRepository
from ecg_aggregator.infrastructure.persistence.session_repository import SessionRepository

logger = get_logger(__name__)


class ECGDatabase:
    """SQLite-backed persistence facade.

    Owns the connection lifecycle and delegates domain operations to focused
    repository objects (SampleRepository, SessionRepository, DeviceRepository,
    AlignmentRepository).
    """

    def __init__(
        self, db_path: Path | str = "ecg_data.db", migrations_dir: Path | str | None = None
    ):
        self.db_path = Path(db_path)
        self._lock = RLock()
        self._conn: sqlite3.Connection | None = None

        self.migrations_dir = (
            Path(migrations_dir) if migrations_dir else Path(__file__).parent / "migrations"
        )

        self._init_db()

        conn = self._get_connection()
        self._samples = SampleRepository(conn, self._lock)
        self._sessions = SessionRepository(conn, self._lock)
        self._devices = DeviceRepository(conn, self._lock)
        self._alignments = AlignmentRepository(conn, self._lock)

        logger.info(f"Initialized ECG database at {self.db_path}")

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        """Initialize database schema using yoyo migrations."""
        self._apply_migrations()
        self._get_connection()

    def _apply_migrations(self) -> None:
        """Apply pending database migrations using yoyo."""
        if not self.migrations_dir.exists():
            logger.warning(
                f"Migrations directory not found: {self.migrations_dir}. Skipping migrations."
            )
            return

        try:
            db_url = f"sqlite:///{self.db_path.absolute()}"
            backend = get_backend(db_url)
            migrations = read_migrations(str(self.migrations_dir))

            with backend.lock():
                pending = backend.to_apply(migrations)
                if pending:
                    logger.info(f"Applying {len(pending)} pending migration(s)")
                    backend.apply_migrations(pending)
                    logger.info("All migrations applied successfully")
                else:
                    logger.debug("No pending migrations")

        except LockTimeout:
            logger.error(
                "Could not acquire migration lock. Another process may be running migrations."
            )
            raise
        except Exception as e:
            logger.error(f"Error applying migrations: {e}")
            raise

    def _get_connection(self) -> sqlite3.Connection:
        """Return the shared SQLite connection, creating it if needed."""
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
        return self._conn

    def close(self) -> None:
        """Close the database connection."""
        with self._lock:
            if self._conn:
                self._conn.close()
                self._conn = None
                logger.info("Database connection closed")

    # ------------------------------------------------------------------
    # Sample operations — delegated to SampleRepository
    # ------------------------------------------------------------------

    def ensure_device(self, device_id: str) -> int:
        return self._samples.ensure_device(device_id)

    def add_sample(
        self,
        device_id: str,
        global_time: GlobalTimeSeconds,
        device_timestamp: DeviceTimestampUs,
        raw_value: int,
        confidence: float,
        session_id: int | None = None,
        wall_clock_us: WallClockUs | None = None,
        receiver_clock_us: ReceiverClockUs | None = None,
        time_verified: bool = False,
    ) -> None:
        self._samples.add_sample(
            device_id=device_id,
            global_time=global_time,
            device_timestamp=device_timestamp,
            raw_value=raw_value,
            confidence=confidence,
            session_id=session_id,
            wall_clock_us=wall_clock_us,
            receiver_clock_us=receiver_clock_us,
            time_verified=time_verified,
        )

    def add_acc_sample(
        self,
        device_id: str,
        global_time: GlobalTimeSeconds,
        device_timestamp: DeviceTimestampUs,
        x: float,
        y: float,
        z: float,
        confidence: float,
        magnitude: float | None = None,
        session_id: int | None = None,
        wall_clock_us: WallClockUs | None = None,
        receiver_clock_us: ReceiverClockUs | None = None,
        time_verified: bool = False,
    ) -> None:
        self._samples.add_acc_sample(
            device_id=device_id,
            global_time=global_time,
            device_timestamp=device_timestamp,
            x=x,
            y=y,
            z=z,
            confidence=confidence,
            magnitude=magnitude,
            session_id=session_id,
            wall_clock_us=wall_clock_us,
            receiver_clock_us=receiver_clock_us,
            time_verified=time_verified,
        )

    def add_ecg_samples_batch(self, samples: list[ECGBatchRow]) -> None:
        self._samples.add_ecg_samples_batch(samples)

    def add_acc_samples_batch(self, samples: list[AccBatchRow]) -> None:
        self._samples.add_acc_samples_batch(samples)

    def get_stats(self) -> dict:
        stats = self._samples.get_stats()
        stats["db_size_bytes"] = self.db_path.stat().st_size if self.db_path.exists() else 0
        stats["db_size_mb"] = stats["db_size_bytes"] / (1024 * 1024)
        return stats

    # ------------------------------------------------------------------
    # Session operations — delegated to SessionRepository
    # ------------------------------------------------------------------

    def create_session(
        self,
        start_time: float | None = None,
        end_time: float | None = None,
        notes: str | None = None,
    ) -> int:
        return self._sessions.create_session(start_time=start_time, end_time=end_time, notes=notes)

    def end_session(self, session_id: int, end_time: float | None = None) -> bool:
        return self._sessions.end_session(session_id, end_time)

    def get_session(self, session_id: int) -> dict | None:
        return self._sessions.get_session(session_id)

    def get_sessions(
        self,
        limit: int | None = None,
        offset: int = 0,
        search: str | None = None,
        active: bool | None = None,
        has_notes: bool | None = None,
        device_id: str | None = None,
        sort_by: SessionSortField = "start_time",
        sort_order: SortOrder = SortOrder.DESC,
    ) -> list[dict]:
        return self._sessions.get_sessions(
            limit=limit,
            offset=offset,
            search=search,
            active=active,
            has_notes=has_notes,
            device_id=device_id,
            sort_by=sort_by,
            sort_order=sort_order,
        )

    def count_sessions(
        self,
        search: str | None = None,
        active: bool | None = None,
        has_notes: bool | None = None,
        device_id: str | None = None,
    ) -> int:
        return self._sessions.count_sessions(
            search=search, active=active, has_notes=has_notes, device_id=device_id
        )

    def update_session(
        self,
        session_id: int,
        end_time: float | None = None,
        notes: str | None = None,
    ) -> bool:
        return self._sessions.update_session(session_id, end_time=end_time, notes=notes)

    def delete_session(self, session_id: int) -> bool:
        return self._sessions.delete_session(session_id)

    def get_session_samples(
        self,
        session_id: int,
        device_id: str | None = None,
        start_time: float | None = None,
        end_time: float | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict]:
        return self._sessions.get_session_samples(
            session_id=session_id,
            device_id=device_id,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            offset=offset,
        )

    def get_session_accelerometer_samples(
        self,
        session_id: int,
        device_id: str | None = None,
        start_time: float | None = None,
        end_time: float | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict]:
        return self._sessions.get_session_accelerometer_samples(
            session_id=session_id,
            device_id=device_id,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            offset=offset,
        )

    def export_session_to_csv(self, session_id: int, output_path: Path | str) -> bool:
        return self._sessions.export_session_to_csv(session_id, output_path)

    def import_session_from_csv(self, input_path: Path | str) -> int | None:
        return self._sessions.import_session_from_csv(input_path)

    # ------------------------------------------------------------------
    # Device & collector operations — delegated to DeviceRepository
    # ------------------------------------------------------------------

    def get_all_devices(self, limit: int | None = None, offset: int = 0) -> list[dict]:
        return self._devices.get_all_devices(limit=limit, offset=offset)

    def count_devices(self) -> int:
        return self._devices.count_devices()

    def update_device_nickname(self, device_id: str, nickname: str | None) -> bool:
        return self._devices.update_device_nickname(device_id, nickname)

    def upsert_collector(
        self,
        collector_id: str,
        display_name: str | None = None,
        version: str | None = None,
        metadata: dict | None = None,
    ) -> bool:
        return self._devices.upsert_collector(
            collector_id=collector_id,
            display_name=display_name,
            version=version,
            metadata=metadata,
        )

    def update_collector_last_seen(self, collector_id: str) -> bool:
        return self._devices.update_collector_last_seen(collector_id)

    def get_all_collectors(self) -> list[dict]:
        return self._devices.get_all_collectors()

    def upsert_device_collector_mapping(self, device_id: str, collector_id: str) -> bool:
        return self._devices.upsert_device_collector_mapping(device_id, collector_id)

    def get_device_collectors(self, device_id: str) -> list[dict]:
        return self._devices.get_device_collectors(device_id)

    # ------------------------------------------------------------------
    # Alignment operations — delegated to AlignmentRepository
    # ------------------------------------------------------------------

    def save_device_alignment(
        self,
        device_id: str,
        time_offset: float,
        confidence: float,
        tap_count: int,
        drift: float = 1.0,
        mean_error: float | None = None,
        std_error: float | None = None,
        offset_version: int | None = None,
    ) -> bool:
        return self._alignments.save_device_alignment(
            device_id=device_id,
            time_offset=time_offset,
            confidence=confidence,
            tap_count=tap_count,
            drift=drift,
            mean_error=mean_error,
            std_error=std_error,
            offset_version=offset_version,
        )

    def get_device_alignment(self, device_id: str) -> dict[str, object] | None:
        return self._alignments.get_device_alignment(device_id)

    def get_all_alignments(self, valid_only: bool = False) -> list[dict[str, object]]:
        return self._alignments.get_all_alignments(valid_only=valid_only)

    def invalidate_device_alignment(self, device_id: str) -> bool:
        return self._alignments.invalidate_device_alignment(device_id)

    def delete_device_alignment(self, device_id: str) -> bool:
        return self._alignments.delete_device_alignment(device_id)
