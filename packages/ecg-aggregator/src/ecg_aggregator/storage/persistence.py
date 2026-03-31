"""SQLite persistence layer for ECG samples."""

import csv
import math
import sqlite3
import time
from pathlib import Path
from threading import RLock

from ecg_common.logging import get_logger
from yoyo import get_backend, read_migrations
from yoyo.backends import DatabaseBackend
from yoyo.exceptions import LockTimeout

from ecg_aggregator.api.models.sessions import SessionSortField
from ecg_aggregator.api.utils import SortOrder

logger = get_logger(__name__)


class ECGDatabase:
    """SQLite database for storing ECG samples."""

    def __init__(
        self, db_path: Path | str = "ecg_data.db", migrations_dir: Path | str | None = None
    ):
        """Initialize the database.

        Args:
            db_path: Path to SQLite database file
            migrations_dir: Path to migrations directory (optional, auto-detected if None)
        """
        self.db_path = Path(db_path)
        self._lock = RLock()
        self._conn: sqlite3.Connection | None = None

        # Auto-detect migrations directory if not provided
        if migrations_dir is None:
            self.migrations_dir = Path(__file__).parent / "migrations"
        else:
            self.migrations_dir = Path(migrations_dir)

        # Create database and run migrations
        self._init_db()

        logger.info(f"Initialized ECG database at {self.db_path}")

    def _init_db(self) -> None:
        """Initialize database schema using yoyo migrations."""
        # Ensure connection exists (creates DB file if needed)
        with self._get_connection() as conn:
            # Enable WAL mode early
            conn.execute("PRAGMA journal_mode=WAL")

        # Apply migrations
        self._apply_migrations()

    def _apply_migrations(self) -> None:
        """Apply pending database migrations using yoyo."""
        if not self.migrations_dir.exists():
            logger.warning(
                f"Migrations directory not found: {self.migrations_dir}. Skipping migrations."
            )
            return

        try:
            # Build SQLite connection URL
            # yoyo expects format: sqlite:////absolute/path/to/db.sqlite
            db_url = f"sqlite:///{self.db_path.absolute()}"

            # Get backend and load migrations
            backend = get_backend(db_url)
            migrations = read_migrations(str(self.migrations_dir))

            # Check if this is a legacy database (has tables but no yoyo tracking)
            is_legacy_db = self._is_legacy_database(backend)

            # Apply migrations with lock
            with backend.lock():
                if is_legacy_db:
                    logger.info(
                        "Detected legacy database. Marking initial schema migration as applied."
                    )
                    # Only mark the initial schema migration (0001) as applied
                    # All other migrations (0002+) should be applied normally
                    initial_migration = [m for m in migrations if "0001_initial_schema" in m.path]
                    if initial_migration:
                        backend.mark_migrations(initial_migration)
                        logger.info("Marked initial schema migration as applied")

                    # Now apply remaining pending migrations
                    pending = backend.to_apply(migrations)
                    if pending:
                        logger.info(f"Applying {len(pending)} pending migration(s)")
                        backend.apply_migrations(pending)
                        logger.info("All migrations applied successfully")
                    else:
                        logger.info("No additional migrations to apply")
                else:
                    # Normal migration application
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

    def _is_legacy_database(self, backend: DatabaseBackend) -> bool:
        """Check if database has tables but no yoyo migration tracking.

        Args:
            backend: Yoyo backend instance

        Returns:
            True if this is a legacy database (has tables but no yoyo tracking)
        """
        try:
            # Check if ecg_samples table exists
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='ecg_samples'"
                )
                has_tables = cursor.fetchone() is not None

            # Check if yoyo tracking table exists by querying for it directly
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='_yoyo_migration'"
                )
                has_yoyo_tracking = cursor.fetchone() is not None

            # Legacy if has tables but no yoyo tracking
            return has_tables and not has_yoyo_tracking

        except Exception:
            return False

    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection (thread-safe).

        Returns:
            SQLite connection
        """
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            # Enable WAL mode for better concurrency
            self._conn.execute("PRAGMA journal_mode=WAL")
        return self._conn

    def _get_or_create_device_id(self, device_id_str: str) -> int:
        """Get or create integer device ID from string device ID.

        Args:
            device_id_str: String device identifier (e.g., "Polar H10 0781CC39")

        Returns:
            Integer device ID for use in sample tables
        """
        with self._lock:
            try:
                conn = self._get_connection()
                cursor = conn.cursor()

                # Try to get existing device
                cursor.execute(
                    "SELECT id FROM devices WHERE device_id = ?",
                    (device_id_str,),
                )
                row = cursor.fetchone()

                if row:
                    return int(row[0])

                # Device doesn't exist, create it
                current_time = time.time()
                cursor.execute(
                    """
                    INSERT INTO devices (device_id, first_seen, last_seen, total_samples)
                    VALUES (?, ?, ?, 0)
                    """,
                    (device_id_str, current_time, current_time),
                )
                conn.commit()

                lastrowid = cursor.lastrowid
                if lastrowid is None:
                    raise RuntimeError(f"Failed to insert device {device_id_str}")
                return lastrowid

            except Exception as e:
                logger.error(f"Error getting/creating device ID for {device_id_str}: {e}")
                raise

    def add_sample(
        self,
        device_id: str,
        global_time: float,
        device_timestamp: float,
        raw_value: int,
        confidence: float,
        session_id: int | None = None,
        wall_clock_us: int | None = None,
        receiver_clock_us: int | None = None,
        time_verified: bool = False,
    ) -> None:
        """Store a single ECG sample.

        Args:
            device_id: Device identifier
            global_time: Synchronized global timestamp
            device_timestamp: Original device timestamp (polar_clock_us)
            raw_value: Raw ECG value
            confidence: Time sync confidence (0-1)
            session_id: Session ID to associate with this sample (optional)
            wall_clock_us: Collector-issued wall clock timestamp (epoch time in microseconds, optional)
            receiver_clock_us: Receiver device clock (microseconds since ESP32/collector boot, optional)
            time_verified: True if polar timestamp came directly from PMD frame (not interpolated, optional)
        """
        # Get integer device ID
        device_id_int = self._get_or_create_device_id(device_id)

        with self._lock:
            try:
                conn = self._get_connection()
                cursor = conn.cursor()

                cursor.execute(
                    """
                    INSERT INTO ecg_samples
                    (device_id, global_time, device_timestamp, raw_value, confidence, session_id, wall_clock_us, receiver_clock_us, time_verified)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        device_id_int,
                        global_time,
                        device_timestamp,
                        raw_value,
                        confidence,
                        session_id,
                        wall_clock_us,
                        receiver_clock_us,
                        1 if time_verified else 0,
                    ),
                )

                # Update device metadata
                cursor.execute(
                    """
                    INSERT INTO devices (device_id, first_seen, last_seen, total_samples)
                    VALUES (?, ?, ?, 1)
                    ON CONFLICT(device_id) DO UPDATE SET
                        last_seen = ?,
                        total_samples = total_samples + 1
                    """,
                    (device_id, global_time, global_time, global_time),
                )

                conn.commit()

            except Exception as e:
                logger.error(f"Error storing sample: {e}")

    def add_acc_sample(
        self,
        device_id: str,
        global_time: float,
        device_timestamp: float,
        x: float,
        y: float,
        z: float,
        confidence: float,
        magnitude: float | None = None,
        session_id: int | None = None,
        wall_clock_us: int | None = None,
        receiver_clock_us: int | None = None,
        time_verified: bool = False,
    ) -> None:
        """Store a single accelerometer sample.

        Args:
            device_id: Device identifier
            global_time: Synchronized global timestamp
            device_timestamp: Original device timestamp (polar_clock_us)
            x: X-axis acceleration (g)
            y: Y-axis acceleration (g)
            z: Z-axis acceleration (g)
            confidence: Time sync confidence (0-1)
            magnitude: Pre-calculated motion magnitude (optional, will be calculated if not provided)
            session_id: Session ID to associate with this sample (optional)
            wall_clock_us: Collector-issued wall clock timestamp (epoch time in microseconds, optional)
            receiver_clock_us: Receiver device clock (microseconds since ESP32/collector boot, optional)
            time_verified: True if polar timestamp came directly from PMD frame (not interpolated, optional)
        """
        # Get integer device ID
        device_id_int = self._get_or_create_device_id(device_id)

        # Calculate magnitude if not provided
        if magnitude is None:
            magnitude = math.sqrt(x**2 + y**2 + z**2)

        with self._lock:
            try:
                conn = self._get_connection()
                cursor = conn.cursor()

                cursor.execute(
                    """
                    INSERT INTO accelerometer_samples
                    (device_id, global_time, device_timestamp, x, y, z, magnitude, confidence, session_id, wall_clock_us, receiver_clock_us, time_verified)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        device_id_int,
                        global_time,
                        device_timestamp,
                        x,
                        y,
                        z,
                        magnitude,
                        confidence,
                        session_id,
                        wall_clock_us,
                        receiver_clock_us,
                        1 if time_verified else 0,
                    ),
                )

                # Update device metadata (same devices table as ECG)
                cursor.execute(
                    """
                    INSERT INTO devices (device_id, first_seen, last_seen, total_samples)
                    VALUES (?, ?, ?, 1)
                    ON CONFLICT(device_id) DO UPDATE SET
                        last_seen = ?,
                        total_samples = total_samples + 1
                    """,
                    (device_id, global_time, global_time, global_time),
                )

                conn.commit()

            except Exception as e:
                logger.error(f"Error storing accelerometer sample: {e}")

    def add_samples_batch(
        self,
        samples: list[
            tuple[str, float, float, int, float, int | None, int | None, int | None, bool]
        ],
    ) -> None:
        """Store multiple ECG samples efficiently.

        Args:
            samples: List of tuples (device_id, global_time, device_timestamp, raw_value, confidence,
                                    session_id, wall_clock_us, receiver_clock_us, time_verified)
        """
        if not samples:
            return

        with self._lock:
            try:
                conn = self._get_connection()
                cursor = conn.cursor()

                # Build device ID mapping and prepare batch data
                device_id_map: dict[str, int] = {}
                for device_id_str, *_ in samples:
                    if device_id_str not in device_id_map:
                        device_id_map[device_id_str] = self._get_or_create_device_id(device_id_str)

                # Prepare batch data with integer device IDs
                sample_data = [
                    (
                        device_id_map[device_id],
                        global_time,
                        device_timestamp,
                        raw_value,
                        confidence,
                        session_id,
                        wall_clock_us,
                        receiver_clock_us,
                        1 if time_verified else 0,
                    )
                    for (
                        device_id,
                        global_time,
                        device_timestamp,
                        raw_value,
                        confidence,
                        session_id,
                        wall_clock_us,
                        receiver_clock_us,
                        time_verified,
                    ) in samples
                ]

                cursor.executemany(
                    """
                    INSERT INTO ecg_samples
                    (device_id, global_time, device_timestamp, raw_value, confidence, session_id, wall_clock_us, receiver_clock_us, time_verified)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    sample_data,
                )

                # Update device metadata for each unique device
                current_time = time.time()
                device_counts: dict[str, int] = {}
                for device_id, *_ in samples:
                    device_counts[device_id] = device_counts.get(device_id, 0) + 1

                for device_id_str, count in device_counts.items():
                    cursor.execute(
                        """
                        INSERT INTO devices (device_id, first_seen, last_seen, total_samples)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(device_id) DO UPDATE SET
                            last_seen = ?,
                            total_samples = total_samples + ?
                        """,
                        (device_id_str, current_time, current_time, count, current_time, count),
                    )

                conn.commit()
                logger.debug(f"Stored {len(samples)} ECG samples in batch")

            except Exception as e:
                logger.error(f"Error storing ECG batch: {e}")

    def add_acc_samples_batch(
        self,
        samples: list[
            tuple[
                str,
                float,
                float,
                float,
                float,
                float,
                float,
                int | None,
                int | None,
                int | None,
                bool,
            ]
        ],
    ) -> None:
        """Store multiple accelerometer samples efficiently.

        Args:
            samples: List of tuples (device_id, global_time, device_timestamp, x, y, z, confidence,
                                    session_id, wall_clock_us, receiver_clock_us, time_verified)
        """
        if not samples:
            return

        with self._lock:
            try:
                conn = self._get_connection()
                cursor = conn.cursor()

                # Build device ID mapping and prepare batch data
                device_id_map: dict[str, int] = {}
                for device_id_str, *_ in samples:
                    if device_id_str not in device_id_map:
                        device_id_map[device_id_str] = self._get_or_create_device_id(device_id_str)

                # Prepare batch data with integer device IDs and calculate magnitudes
                sample_data = []
                for (
                    device_id,
                    global_time,
                    device_timestamp,
                    x,
                    y,
                    z,
                    confidence,
                    session_id,
                    wall_clock_us,
                    receiver_clock_us,
                    time_verified,
                ) in samples:
                    magnitude = math.sqrt(x**2 + y**2 + z**2)
                    sample_data.append(
                        (
                            device_id_map[device_id],
                            global_time,
                            device_timestamp,
                            x,
                            y,
                            z,
                            magnitude,
                            confidence,
                            session_id,
                            wall_clock_us,
                            receiver_clock_us,
                            1 if time_verified else 0,
                        )
                    )

                cursor.executemany(
                    """
                    INSERT INTO accelerometer_samples
                    (device_id, global_time, device_timestamp, x, y, z, magnitude, confidence, session_id, wall_clock_us, receiver_clock_us, time_verified)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    sample_data,
                )

                # Update device metadata for each unique device
                current_time = time.time()
                device_counts: dict[str, int] = {}
                for device_id, *_ in samples:
                    device_counts[device_id] = device_counts.get(device_id, 0) + 1

                for device_id_str, count in device_counts.items():
                    cursor.execute(
                        """
                        INSERT INTO devices (device_id, first_seen, last_seen, total_samples)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(device_id) DO UPDATE SET
                            last_seen = ?,
                            total_samples = total_samples + ?
                        """,
                        (device_id_str, current_time, current_time, count, current_time, count),
                    )

                conn.commit()
                logger.debug(f"Stored {len(samples)} accelerometer samples in batch")

            except Exception as e:
                logger.error(f"Error storing accelerometer batch: {e}")

    def get_samples(
        self,
        device_id: str | None = None,
        start_time: float | None = None,
        end_time: float | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        """Retrieve ECG samples from database.

        Args:
            device_id: Filter by device ID (optional)
            start_time: Filter by start time (optional)
            end_time: Filter by end time (optional)
            limit: Maximum number of samples to return (optional)

        Returns:
            List of sample dictionaries
        """
        with self._lock:
            try:
                conn = self._get_connection()
                cursor = conn.cursor()

                query = """
                    SELECT d.device_id, e.global_time, e.device_timestamp, e.raw_value, e.confidence
                    FROM ecg_samples e
                    JOIN devices d ON e.device_id = d.id
                    WHERE 1=1
                """
                params: list[str | float | int] = []

                if device_id:
                    query += " AND d.device_id = ?"
                    params.append(device_id)

                if start_time:
                    query += " AND e.global_time >= ?"
                    params.append(start_time)

                if end_time:
                    query += " AND e.global_time <= ?"
                    params.append(end_time)

                query += " ORDER BY e.global_time ASC"

                if limit:
                    query += " LIMIT ?"
                    params.append(limit)

                cursor.execute(query, params)

                results = []
                for row in cursor.fetchall():
                    results.append(
                        {
                            "device_id": row[0],
                            "global_time": row[1],
                            "device_timestamp": row[2],
                            "raw_value": row[3],
                            "confidence": row[4],
                        }
                    )

                return results

            except Exception as e:
                logger.error(f"Error retrieving samples: {e}")
                return []

    def get_stats(self) -> dict:
        """Get database statistics.

        Returns:
            Dictionary with database stats
        """
        with self._lock:
            try:
                conn = self._get_connection()
                cursor = conn.cursor()

                # Total samples
                cursor.execute("SELECT COUNT(*) FROM ecg_samples")
                total_samples = cursor.fetchone()[0]

                # Time range
                cursor.execute("SELECT MIN(global_time), MAX(global_time) FROM ecg_samples")
                time_range = cursor.fetchone()

                # Device stats
                cursor.execute("""
                    SELECT device_id, total_samples, first_seen, last_seen
                    FROM devices
                """)
                devices = {}
                for row in cursor.fetchall():
                    devices[row[0]] = {
                        "total_samples": row[1],
                        "first_seen": row[2],
                        "last_seen": row[3],
                    }

                # Database file size
                db_size = self.db_path.stat().st_size if self.db_path.exists() else 0

                return {
                    "total_samples": total_samples,
                    "time_range": {
                        "start": time_range[0],
                        "end": time_range[1],
                        "duration": (time_range[1] - time_range[0])
                        if time_range[0] and time_range[1]
                        else 0,
                    },
                    "devices": devices,
                    "db_size_bytes": db_size,
                    "db_size_mb": db_size / (1024 * 1024),
                }

            except Exception as e:
                logger.error(f"Error getting stats: {e}")
                return {}

    def update_unsynced_samples(
        self,
        device_id: str,
        offset: float,
    ) -> int:
        """Update unsynced samples with calculated offset.

        Args:
            device_id: Device identifier
            offset: Time offset to apply (global_time = device_timestamp + offset)

        Returns:
            Number of samples updated
        """
        with self._lock:
            try:
                conn = self._get_connection()
                cursor = conn.cursor()

                # Update samples where confidence is 0 (unsynced)
                cursor.execute(
                    """
                    UPDATE ecg_samples
                    SET global_time = device_timestamp + ?,
                        confidence = 1.0
                    WHERE device_id = ? AND confidence = 0.0
                    """,
                    (offset, device_id),
                )

                updated = cursor.rowcount
                conn.commit()

                if updated > 0:
                    logger.info(
                        f"Updated {updated} unsynced samples for {device_id} with offset {offset:.3f}s"
                    )
                return updated

            except Exception as e:
                logger.error(f"Error updating unsynced samples: {e}")
                return 0

    def delete_old_samples(self, before_time: float) -> int:
        """Delete samples older than specified time.

        Args:
            before_time: Delete samples before this timestamp

        Returns:
            Number of samples deleted
        """
        with self._lock:
            try:
                conn = self._get_connection()
                cursor = conn.cursor()

                cursor.execute("DELETE FROM ecg_samples WHERE global_time < ?", (before_time,))

                deleted = cursor.rowcount
                conn.commit()

                logger.info(f"Deleted {deleted} old samples")
                return deleted

            except Exception as e:
                logger.error(f"Error deleting old samples: {e}")
                return 0

    def vacuum(self) -> None:
        """Optimize database (reclaim space after deletions)."""
        with self._lock:
            try:
                conn = self._get_connection()
                conn.execute("VACUUM")
                logger.info("Database vacuumed")
            except Exception as e:
                logger.error(f"Error vacuuming database: {e}")

    # Session management methods

    def create_session(
        self,
        start_time: float | None = None,
        end_time: float | None = None,
        notes: str | None = None,
    ) -> int:
        """Create a new recording session.

        Args:
            start_time: Session start timestamp (defaults to current time)
            end_time: Session end timestamp (optional)
            notes: Session notes (optional)

        Returns:
            Session ID, or -1 on error
        """
        with self._lock:
            try:
                conn = self._get_connection()
                cursor = conn.cursor()

                if start_time is None:
                    start_time = time.time()

                cursor.execute(
                    """
                    INSERT INTO sessions (start_time, end_time, notes)
                    VALUES (?, ?, ?)
                    """,
                    (start_time, end_time, notes),
                )

                session_id = cursor.lastrowid
                conn.commit()

                logger.info(f"Created session {session_id}")
                return session_id if session_id is not None else -1

            except Exception as e:
                logger.error(f"Error creating session: {e}")
                return -1

    def _calculate_session_stats(self, cursor: sqlite3.Cursor, session_id: int) -> tuple[int, int]:
        """Calculate sample count and device count for a session.

        Args:
            cursor: Database cursor
            session_id: Session ID

        Returns:
            Tuple of (sample_count, device_count)
        """
        # Calculate sample count from ECG and accelerometer samples
        cursor.execute(
            "SELECT COUNT(*) FROM ecg_samples WHERE session_id = ?",
            (session_id,),
        )
        ecg_count = cursor.fetchone()[0]

        cursor.execute(
            "SELECT COUNT(*) FROM accelerometer_samples WHERE session_id = ?",
            (session_id,),
        )
        acc_count = cursor.fetchone()[0]

        total_sample_count = ecg_count + acc_count

        # Calculate device count (unique devices across both sample types)
        cursor.execute(
            """
            SELECT COUNT(DISTINCT device_id) FROM (
                SELECT device_id FROM ecg_samples WHERE session_id = ?
                UNION
                SELECT device_id FROM accelerometer_samples WHERE session_id = ?
            )
            """,
            (session_id, session_id),
        )
        device_count = cursor.fetchone()[0]

        return total_sample_count, device_count

    def end_session(self, session_id: int, end_time: float | None = None) -> bool:
        """End a recording session by setting its end time.

        Args:
            session_id: Session ID to end
            end_time: End timestamp (defaults to current time)

        Returns:
            True if successful, False otherwise
        """
        with self._lock:
            try:
                conn = self._get_connection()
                cursor = conn.cursor()

                if end_time is None:
                    end_time = time.time()

                # Get session start time
                cursor.execute("SELECT start_time FROM sessions WHERE id = ?", (session_id,))
                result = cursor.fetchone()
                if not result:
                    logger.error(f"Session {session_id} not found")
                    return False
                start_time = result[0]

                # Clean up samples outside session time bounds
                # Remove session_id from ECG samples that fall outside [start_time, end_time]
                cursor.execute(
                    """
                    UPDATE ecg_samples
                    SET session_id = NULL
                    WHERE session_id = ? AND (global_time < ? OR global_time > ?)
                    """,
                    (session_id, start_time, end_time),
                )
                ecg_cleaned = cursor.rowcount

                # Remove session_id from accelerometer samples that fall outside [start_time, end_time]
                cursor.execute(
                    """
                    UPDATE accelerometer_samples
                    SET session_id = NULL
                    WHERE session_id = ? AND (global_time < ? OR global_time > ?)
                    """,
                    (session_id, start_time, end_time),
                )
                acc_cleaned = cursor.rowcount

                if ecg_cleaned > 0 or acc_cleaned > 0:
                    logger.info(
                        f"Cleaned up {ecg_cleaned} ECG and {acc_cleaned} ACC samples "
                        f"outside session {session_id} time bounds"
                    )

                # Calculate session statistics (after cleanup)
                sample_count, device_count = self._calculate_session_stats(cursor, session_id)

                # Update session with end time and calculated stats
                cursor.execute(
                    """
                    UPDATE sessions
                    SET end_time = ?, sample_count = ?, device_count = ?
                    WHERE id = ?
                    """,
                    (end_time, sample_count, device_count, session_id),
                )

                conn.commit()

                logger.info(
                    f"Ended session {session_id} at {end_time} "
                    f"({sample_count} samples, {device_count} devices)"
                )
                return True

            except Exception as e:
                logger.error(f"Error ending session: {e}")
                return False

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
        """Retrieve all sessions.

        Args:
            limit: Maximum number of sessions to return
            offset: Number of sessions to skip
            search: Optional notes search
            active: Filter active/completed sessions
            has_notes: Filter sessions with/without notes
            device_id: Filter sessions containing a specific device
            sort_by: Sort field
            sort_order: Sort direction

        Returns:
            List of session dictionaries
        """
        with self._lock:
            try:
                conn = self._get_connection()
                cursor = conn.cursor()

                where_clause, params = self._build_sessions_filter_clause(
                    search=search,
                    active=active,
                    has_notes=has_notes,
                    device_id=device_id,
                )
                order_by = self._build_sessions_order_clause(
                    sort_by=sort_by,
                    sort_order=sort_order,
                )

                query = (
                    "SELECT s.id, s.start_time, s.end_time, s.device_count, s.sample_count, s.notes "
                    "FROM sessions s"
                )
                if where_clause:
                    query += f" WHERE {where_clause}"
                query += f" ORDER BY {order_by}"

                if limit is not None:
                    query += " LIMIT ? OFFSET ?"
                    params.extend([limit, offset])

                cursor.execute(query, params)
                rows = cursor.fetchall()

                if not rows:
                    return []

                # Extract session IDs
                session_ids = [row[0] for row in rows]

                # Batch query 1: Get ECG sample counts for all sessions
                ecg_counts: dict[int, int] = {}
                if session_ids:
                    placeholders = ",".join("?" * len(session_ids))
                    cursor.execute(
                        f"""
                        SELECT session_id, COUNT(*)
                        FROM ecg_samples
                        WHERE session_id IN ({placeholders})
                        GROUP BY session_id
                        """,
                        session_ids,
                    )
                    ecg_counts = dict(cursor.fetchall())

                # Batch query 2: Get ACC sample counts for all sessions
                acc_counts: dict[int, int] = {}
                if session_ids:
                    placeholders = ",".join("?" * len(session_ids))
                    cursor.execute(
                        f"""
                        SELECT session_id, COUNT(*)
                        FROM accelerometer_samples
                        WHERE session_id IN ({placeholders})
                        GROUP BY session_id
                        """,
                        session_ids,
                    )
                    acc_counts = dict(cursor.fetchall())

                # Batch query 3: Get devices for all sessions
                session_devices: dict[int, list[str]] = {sid: [] for sid in session_ids}
                if session_ids:
                    placeholders = ",".join("?" * len(session_ids))
                    cursor.execute(
                        f"""
                        SELECT e.session_id, d.device_id
                        FROM ecg_samples e
                        JOIN devices d ON e.device_id = d.id
                        WHERE e.session_id IN ({placeholders})
                        GROUP BY e.session_id, d.device_id
                        UNION
                        SELECT a.session_id, d.device_id
                        FROM accelerometer_samples a
                        JOIN devices d ON a.device_id = d.id
                        WHERE a.session_id IN ({placeholders})
                        GROUP BY a.session_id, d.device_id
                        """,
                        session_ids + session_ids,
                    )
                    for session_id, device_id in cursor.fetchall():
                        session_devices[session_id].append(device_id)

                # Build results
                results = []
                for row in rows:
                    session_id = row[0]

                    # Get sample counts from batch queries
                    ecg_count = ecg_counts.get(session_id, 0)
                    acc_count = acc_counts.get(session_id, 0)
                    devices_list = session_devices.get(session_id, [])

                    session_data = {
                        "id": session_id,
                        "start_time": row[1],
                        "end_time": row[2],
                        "notes": row[5],
                        "ecg_sample_count": ecg_count,
                        "acc_sample_count": acc_count,
                        "devices": devices_list,
                    }

                    # Calculate duration
                    if row[2]:  # end_time
                        session_data["duration_seconds"] = row[2] - row[1]
                    else:
                        session_data["duration_seconds"] = None

                    # Use stored counts if available, otherwise calculate from batch results
                    if row[3] is not None and row[4] is not None:
                        session_data["device_count"] = row[3]
                        session_data["sample_count"] = row[4]
                    else:
                        calculated_sample_count = ecg_count + acc_count
                        calculated_device_count = len(devices_list)
                        session_data["sample_count"] = calculated_sample_count
                        session_data["device_count"] = calculated_device_count

                        # Update the database with calculated values
                        cursor.execute(
                            """
                            UPDATE sessions
                            SET device_count = ?, sample_count = ?
                            WHERE id = ?
                            """,
                            (calculated_device_count, calculated_sample_count, session_id),
                        )
                        conn.commit()
                        logger.debug(
                            f"Session {session_id}: Updated counts in DB - device_count={calculated_device_count}, sample_count={calculated_sample_count}"
                        )

                    results.append(session_data)

                return results

            except Exception as e:
                logger.error(f"Error retrieving sessions: {e}")
                return []

    def count_sessions(self) -> int:
        """Count sessions matching optional filters."""
        return self.count_sessions_filtered()

    def count_sessions_filtered(
        self,
        search: str | None = None,
        active: bool | None = None,
        has_notes: bool | None = None,
        device_id: str | None = None,
    ) -> int:
        """Count sessions matching filters."""
        with self._lock:
            try:
                conn = self._get_connection()
                cursor = conn.cursor()
                where_clause, params = self._build_sessions_filter_clause(
                    search=search,
                    active=active,
                    has_notes=has_notes,
                    device_id=device_id,
                )
                query = "SELECT COUNT(*) FROM sessions s"
                if where_clause:
                    query += f" WHERE {where_clause}"
                cursor.execute(query, params)
                row = cursor.fetchone()
                return int(row[0]) if row else 0
            except Exception as e:
                logger.error(f"Error counting sessions: {e}")
                return 0

    def _build_sessions_filter_clause(
        self,
        search: str | None = None,
        active: bool | None = None,
        has_notes: bool | None = None,
        device_id: str | None = None,
    ) -> tuple[str, list[object]]:
        """Build reusable WHERE clause for session list queries."""
        clauses: list[str] = []
        params: list[object] = []

        if search:
            clauses.append("LOWER(COALESCE(s.notes, '')) LIKE ?")
            params.append(f"%{search.lower()}%")

        if active is not None:
            clauses.append("s.end_time IS NULL" if active else "s.end_time IS NOT NULL")

        if has_notes is not None:
            clauses.append(
                "s.notes IS NOT NULL AND TRIM(s.notes) != ''"
                if has_notes
                else "(s.notes IS NULL OR TRIM(s.notes) = '')"
            )

        if device_id:
            clauses.append(
                """
                (
                    EXISTS (
                        SELECT 1
                        FROM ecg_samples e
                        JOIN devices d ON e.device_id = d.id
                        WHERE e.session_id = s.id AND d.device_id = ?
                    )
                    OR EXISTS (
                        SELECT 1
                        FROM accelerometer_samples a
                        JOIN devices d ON a.device_id = d.id
                        WHERE a.session_id = s.id AND d.device_id = ?
                    )
                )
                """
            )
            params.extend([device_id, device_id])

        return " AND ".join(clauses), params

    def _build_sessions_order_clause(
        self,
        sort_by: SessionSortField = "start_time",
        sort_order: SortOrder = SortOrder.DESC,
    ) -> str:
        """Build safe ORDER BY clause for session list queries."""
        sort_columns: dict[str, str] = {
            "id": "s.id",
            "start_time": "s.start_time",
            "end_time": "s.end_time",
            "device_count": "s.device_count",
            "sample_count": "s.sample_count",
        }
        direction = "ASC" if sort_order is SortOrder.ASC else "DESC"
        column = sort_columns.get(sort_by, "s.start_time")
        return f"{column} {direction}, s.id DESC"

    def get_session(self, session_id: int) -> dict | None:
        """Get a single session by ID.

        Args:
            session_id: Session ID

        Returns:
            Session dictionary or None if not found
        """
        with self._lock:
            try:
                conn = self._get_connection()
                cursor = conn.cursor()

                cursor.execute(
                    """
                    SELECT id, start_time, end_time, device_count, sample_count, notes
                    FROM sessions WHERE id = ?
                    """,
                    (session_id,),
                )

                row = cursor.fetchone()
                if not row:
                    return None

                session_data = {
                    "id": row[0],
                    "start_time": row[1],
                    "end_time": row[2],
                    "device_count": row[3],
                    "sample_count": row[4],
                    "notes": row[5],
                }

                # Calculate duration
                if row[2]:
                    session_data["duration_seconds"] = row[2] - row[1]
                else:
                    session_data["duration_seconds"] = None

                # If device_count or sample_count is NULL (active session), calculate on-the-fly
                if row[3] is None or row[4] is None:
                    sample_count, device_count = self._calculate_session_stats(cursor, session_id)
                    session_data["sample_count"] = sample_count
                    session_data["device_count"] = device_count

                # Get separate ECG and ACC sample counts
                cursor.execute(
                    "SELECT COUNT(*) FROM ecg_samples WHERE session_id = ?",
                    (session_id,),
                )
                session_data["ecg_sample_count"] = cursor.fetchone()[0]

                cursor.execute(
                    "SELECT COUNT(*) FROM accelerometer_samples WHERE session_id = ?",
                    (session_id,),
                )
                session_data["acc_sample_count"] = cursor.fetchone()[0]

                # Get unique devices
                cursor.execute(
                    """
                    SELECT DISTINCT d.device_id FROM ecg_samples e
                    JOIN devices d ON e.device_id = d.id
                    WHERE e.session_id = ?
                    UNION
                    SELECT DISTINCT d.device_id FROM accelerometer_samples a
                    JOIN devices d ON a.device_id = d.id
                    WHERE a.session_id = ?
                    """,
                    (session_id, session_id),
                )
                devices = [d[0] for d in cursor.fetchall()]
                session_data["devices"] = devices

                return session_data

            except Exception as e:
                logger.error(f"Error retrieving session: {e}")
                return None

    def update_session(
        self,
        session_id: int,
        end_time: float | None = None,
        notes: str | None = None,
    ) -> bool:
        """Update session metadata.

        Args:
            session_id: Session ID
            end_time: Session end time
            notes: Session notes

        Returns:
            True if successful
        """
        with self._lock:
            try:
                conn = self._get_connection()
                cursor = conn.cursor()

                updates = []
                params: list[float | str | int] = []

                if end_time is not None:
                    updates.append("end_time = ?")
                    params.append(end_time)

                if notes is not None:
                    updates.append("notes = ?")
                    params.append(notes)

                if not updates:
                    return True

                params.append(session_id)
                query = f"UPDATE sessions SET {', '.join(updates)} WHERE id = ?"

                cursor.execute(query, params)
                conn.commit()

                return True

            except Exception as e:
                logger.error(f"Error updating session: {e}")
                return False

    def delete_session(self, session_id: int) -> bool:
        """Delete a session and optionally its samples.

        Args:
            session_id: Session ID

        Returns:
            True if successful
        """
        with self._lock:
            try:
                conn = self._get_connection()
                cursor = conn.cursor()

                # Delete session (samples will have session_id set to NULL due to cascade)
                cursor.execute("DELETE FROM sessions WHERE id = ?", (session_id,))

                # Optionally unlink samples instead of deleting them
                cursor.execute(
                    "UPDATE ecg_samples SET session_id = NULL WHERE session_id = ?",
                    (session_id,),
                )

                conn.commit()
                logger.info(f"Deleted session {session_id}")
                return True

            except Exception as e:
                logger.error(f"Error deleting session: {e}")
                return False

    def get_session_samples(
        self,
        session_id: int,
        device_id: str | None = None,
        start_time: float | None = None,
        end_time: float | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict]:
        """Get samples for a specific session.

        Args:
            session_id: Session ID
            device_id: Filter by device ID (optional)
            start_time: Start of time range in Unix timestamp (optional)
            end_time: End of time range in Unix timestamp (optional)
            limit: Maximum samples to return
            offset: Number of samples to skip

        Returns:
            List of sample dictionaries
        """
        with self._lock:
            try:
                conn = self._get_connection()
                cursor = conn.cursor()

                query = """
                    SELECT e.id, d.device_id, e.global_time, e.raw_value, e.confidence, e.wall_clock_us, e.receiver_clock_us, e.device_timestamp, e.time_verified
                    FROM ecg_samples e
                    JOIN devices d ON e.device_id = d.id
                    WHERE e.session_id = ?
                """
                params: list[int | str | float] = [session_id]

                if device_id:
                    query += " AND d.device_id = ?"
                    params.append(device_id)

                if start_time is not None:
                    query += " AND e.global_time >= ?"
                    params.append(start_time)

                if end_time is not None:
                    query += " AND e.global_time <= ?"
                    params.append(end_time)

                query += " ORDER BY e.global_time ASC"

                if limit:
                    query += " LIMIT ? OFFSET ?"
                    params.extend([limit, offset])

                cursor.execute(query, params)

                results = []
                for row in cursor.fetchall():
                    results.append(
                        {
                            "id": row[0],
                            "device_id": row[1],
                            "global_time": row[2],
                            "raw_value": row[3],
                            "confidence": row[4],
                            "wall_clock_us": row[5],
                            "receiver_clock_us": row[6],
                            "polar_clock_us": row[7],
                            "time_verified": bool(row[8]),
                        }
                    )

                return results

            except Exception as e:
                logger.error(f"Error retrieving session samples: {e}")
                return []

    def get_session_accelerometer_samples(
        self,
        session_id: int,
        device_id: str | None = None,
        start_time: float | None = None,
        end_time: float | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict]:
        """Get accelerometer samples for a specific session.

        Args:
            session_id: Session ID
            device_id: Filter by device ID (optional)
            start_time: Start of time range in Unix timestamp (optional)
            end_time: End of time range in Unix timestamp (optional)
            limit: Maximum samples to return
            offset: Number of samples to skip

        Returns:
            List of accelerometer sample dictionaries
        """
        with self._lock:
            try:
                conn = self._get_connection()
                cursor = conn.cursor()

                query = """
                    SELECT a.id, d.device_id, a.global_time, a.x, a.y, a.z, a.magnitude, a.confidence, a.wall_clock_us, a.receiver_clock_us, a.device_timestamp, a.time_verified
                    FROM accelerometer_samples a
                    JOIN devices d ON a.device_id = d.id
                    WHERE a.session_id = ?
                """
                params: list[int | str | float] = [session_id]

                if device_id:
                    query += " AND d.device_id = ?"
                    params.append(device_id)

                if start_time is not None:
                    query += " AND a.global_time >= ?"
                    params.append(start_time)

                if end_time is not None:
                    query += " AND a.global_time <= ?"
                    params.append(end_time)

                query += " ORDER BY a.global_time ASC"

                if limit:
                    query += " LIMIT ? OFFSET ?"
                    params.extend([limit, offset])

                cursor.execute(query, params)

                results = []
                for row in cursor.fetchall():
                    results.append(
                        {
                            "id": row[0],
                            "device_id": row[1],
                            "global_time": row[2],
                            "x": row[3],
                            "y": row[4],
                            "z": row[5],
                            "magnitude": row[6],
                            "confidence": row[7],
                            "wall_clock_us": row[8],
                            "receiver_clock_us": row[9],
                            "polar_clock_us": row[10],
                            "time_verified": bool(row[11]),
                        }
                    )

                return results

            except Exception as e:
                logger.error(f"Error retrieving session accelerometer samples: {e}")
                return []

    def create_sessions_from_samples(
        self, gap_threshold: float = 300.0, min_duration: float = 30.0
    ) -> int:
        """Analyze existing samples and create sessions based on time gaps.

        Args:
            gap_threshold: Time gap in seconds to consider a new session (default: 5 minutes)
            min_duration: Minimum session duration in seconds to keep (default: 30 seconds)

        Returns:
            Number of sessions created
        """
        with self._lock:
            try:
                conn = self._get_connection()
                cursor = conn.cursor()

                # Get all samples ordered by time
                cursor.execute(
                    """
                    SELECT id, device_id, global_time
                    FROM ecg_samples
                    WHERE session_id IS NULL
                    ORDER BY global_time ASC
                    """
                )

                samples = cursor.fetchall()
                if not samples:
                    logger.info("No unassigned samples to process")
                    return 0

                sessions_created = 0
                sessions_discarded = 0
                current_session_id: int | None = None
                current_session_start: float | None = None
                current_session_end: float | None = None
                last_time: float | None = None
                session_sample_ids: list[int] = []

                def save_current_session() -> None:
                    """Helper to save or discard current session based on duration."""
                    nonlocal sessions_created, sessions_discarded, current_session_id

                    if not current_session_id or not session_sample_ids:
                        return

                    if current_session_end is None or current_session_start is None:
                        return

                    session_duration = current_session_end - current_session_start

                    if session_duration < min_duration:
                        # Discard short session - delete it and leave samples unassigned
                        cursor.execute("DELETE FROM sessions WHERE id = ?", (current_session_id,))
                        sessions_discarded += 1
                        logger.debug(
                            f"Discarded session {current_session_id} (duration: {session_duration:.1f}s < {min_duration}s)"
                        )
                    else:
                        # Keep session - update end time and assign samples
                        cursor.execute(
                            "UPDATE sessions SET end_time = ? WHERE id = ?",
                            (current_session_end, current_session_id),
                        )
                        cursor.executemany(
                            "UPDATE ecg_samples SET session_id = ? WHERE id = ?",
                            [(current_session_id, sid) for sid in session_sample_ids],
                        )

                for sample_id, _device_id, global_time in samples:
                    # Check if we need to start a new session
                    if last_time is None or (global_time - last_time) > gap_threshold:
                        # Save previous session (may be discarded if too short)
                        save_current_session()

                        # Create new session
                        cursor.execute(
                            "INSERT INTO sessions (start_time) VALUES (?)",
                            (global_time,),
                        )
                        current_session_id = cursor.lastrowid
                        current_session_start = global_time
                        session_sample_ids = []
                        sessions_created += 1

                    # Add sample to current session
                    session_sample_ids.append(sample_id)
                    current_session_end = global_time
                    last_time = global_time

                # Save final session (may be discarded if too short)
                save_current_session()

                # Update session statistics
                cursor.execute(
                    """
                    UPDATE sessions
                    SET sample_count = (
                        SELECT COUNT(*) FROM ecg_samples WHERE session_id = sessions.id
                    ),
                    device_count = (
                        SELECT COUNT(DISTINCT device_id) FROM ecg_samples WHERE session_id = sessions.id
                    )
                    WHERE id IN (
                        SELECT DISTINCT session_id FROM ecg_samples WHERE session_id IS NOT NULL
                    )
                    """
                )

                conn.commit()
                logger.info(
                    f"Created {sessions_created} sessions from existing samples "
                    f"({sessions_discarded} discarded as too short)"
                )
                return sessions_created

            except Exception as e:
                logger.error(f"Error creating sessions from samples: {e}")
                return 0

    def export_session_to_csv(self, session_id: int, output_path: Path | str) -> bool:
        """Export a session's samples to CSV format.

        Args:
            session_id: Session ID to export
            output_path: Path to output CSV file

        Returns:
            True if successful, False otherwise
        """
        output_path = Path(output_path)

        with self._lock:
            try:
                # Get session metadata
                session = self.get_session(session_id)
                if not session:
                    logger.error(f"Session {session_id} not found")
                    return False

                # Get all samples for the session
                samples = self.get_session_samples(session_id=session_id)
                if not samples:
                    logger.warning(f"Session {session_id} has no samples")
                    return False

                # Write CSV with metadata header
                with open(output_path, "w", newline="") as csvfile:
                    writer = csv.writer(csvfile)

                    # Write metadata as comments
                    writer.writerow(["# Session Export"])
                    writer.writerow(["# session_id", session_id])
                    writer.writerow(["# start_time", session["start_time"]])
                    writer.writerow(["# end_time", session["end_time"]])
                    writer.writerow(["# duration_seconds", session["duration_seconds"]])
                    writer.writerow(["# sample_count", session["sample_count"]])
                    writer.writerow(["# device_count", session["device_count"]])
                    writer.writerow(["# devices", ",".join(session["devices"])])
                    writer.writerow([])

                    # Write column headers
                    writer.writerow(["device_id", "global_time", "raw_value", "confidence"])

                    # Write sample data
                    for sample in samples:
                        writer.writerow(
                            [
                                sample["device_id"],
                                sample["global_time"],
                                sample["raw_value"],
                                sample["confidence"],
                            ]
                        )

                logger.info(
                    f"Exported session {session_id} ({len(samples)} samples) to {output_path}"
                )
                return True

            except Exception as e:
                logger.error(f"Error exporting session to CSV: {e}")
                return False

    def import_session_from_csv(self, input_path: Path | str) -> int | None:
        """Import a session from CSV format.

        Args:
            input_path: Path to input CSV file

        Returns:
            Session ID of imported session, or None if failed
        """
        input_path = Path(input_path)

        if not input_path.exists():
            logger.error(f"CSV file not found: {input_path}")
            return None

        with self._lock:
            try:
                conn = self._get_connection()
                cursor = conn.cursor()

                # Read CSV and parse metadata
                metadata = {}
                samples_data = []

                with open(input_path, newline="") as csvfile:
                    reader = csv.reader(csvfile)

                    # Parse metadata from comment lines
                    in_metadata = True
                    for row in reader:
                        if not row:
                            continue

                        # Check if metadata line
                        if row[0].startswith("#"):
                            if len(row) >= 2 and row[0] == "# session_id":
                                continue  # Skip session_id, we'll create a new one
                            elif len(row) >= 2:
                                key = row[0][2:]  # Remove "# " prefix
                                value = row[1] if len(row) > 1 else None
                                metadata[key] = value
                            continue

                        # Column header row
                        if in_metadata and row[0] == "device_id":
                            in_metadata = False
                            continue

                        # Sample data row
                        if not in_metadata:
                            samples_data.append(
                                {
                                    "device_id": row[0],
                                    "global_time": float(row[1]),
                                    "raw_value": int(float(row[2])),
                                    "confidence": int(float(row[3])),
                                }
                            )

                if not samples_data:
                    logger.error("No sample data found in CSV")
                    return None

                # Create new session
                start_time_value = metadata.get("start_time")
                start_time = (
                    float(start_time_value)
                    if start_time_value is not None
                    else samples_data[0]["global_time"]
                )
                cursor.execute("INSERT INTO sessions (start_time) VALUES (?)", (start_time,))
                session_id = cursor.lastrowid

                # Import samples
                for sample in samples_data:
                    # Get integer device ID
                    device_id_str = str(sample["device_id"])
                    device_id_int = self._get_or_create_device_id(device_id_str)

                    cursor.execute(
                        """
                        INSERT INTO ecg_samples (device_id, global_time, device_timestamp, raw_value, confidence, session_id)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            device_id_int,
                            sample["global_time"],
                            sample[
                                "global_time"
                            ],  # Use global_time as device_timestamp for imported data
                            sample["raw_value"],
                            sample["confidence"],
                            session_id,
                        ),
                    )

                # Update session end_time and statistics
                end_time_value = metadata.get("end_time")
                end_time = (
                    float(end_time_value)
                    if end_time_value is not None
                    else samples_data[-1]["global_time"]
                )
                cursor.execute(
                    """
                    UPDATE sessions
                    SET end_time = ?,
                        sample_count = (SELECT COUNT(*) FROM ecg_samples WHERE session_id = ?),
                        device_count = (SELECT COUNT(DISTINCT device_id) FROM ecg_samples WHERE session_id = ?)
                    WHERE id = ?
                    """,
                    (end_time, session_id, session_id, session_id),
                )

                conn.commit()
                logger.info(
                    f"Imported session {session_id} ({len(samples_data)} samples) from {input_path}"
                )
                return session_id

            except Exception as e:
                logger.error(f"Error importing session from CSV: {e}")
                return None

    def get_all_devices(self, limit: int | None = None, offset: int = 0) -> list[dict]:
        """Get all known devices from database.

        Returns:
            List of device dictionaries with metadata
        """
        with self._lock:
            try:
                conn = self._get_connection()
                cursor = conn.cursor()

                query = """
                    SELECT device_id, first_seen, last_seen, total_samples, nickname
                    FROM devices
                    ORDER BY last_seen DESC
                """
                params: list[int] = []
                if limit is not None:
                    query += " LIMIT ? OFFSET ?"
                    params.extend([limit, offset])

                cursor.execute(query, params)

                results = []
                for row in cursor.fetchall():
                    results.append(
                        {
                            "device_id": row[0],
                            "first_seen": row[1],
                            "last_seen": row[2],
                            "total_samples": row[3],
                            "nickname": row[4],
                        }
                    )

                return results

            except Exception as e:
                logger.error(f"Error retrieving devices: {e}")
                return []

    def count_devices(self) -> int:
        """Count all known devices in the database."""
        with self._lock:
            try:
                conn = self._get_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM devices")
                row = cursor.fetchone()
                return int(row[0]) if row else 0
            except Exception as e:
                logger.error(f"Error counting devices: {e}")
                return 0

    def update_device_nickname(self, device_id: str, nickname: str | None) -> bool:
        """Update a device's nickname.

        Creates the device entry if it doesn't exist yet.

        Args:
            device_id: Device identifier
            nickname: New nickname (or None to clear)

        Returns:
            True if successful
        """
        with self._lock:
            try:
                conn = self._get_connection()
                cursor = conn.cursor()

                # Use INSERT OR IGNORE to create device if it doesn't exist, then UPDATE
                current_time = time.time()
                cursor.execute(
                    """
                    INSERT INTO devices (device_id, first_seen, last_seen, total_samples)
                    VALUES (?, ?, ?, 0)
                    ON CONFLICT(device_id) DO NOTHING
                    """,
                    (device_id, current_time, current_time),
                )

                # Now update the nickname
                cursor.execute(
                    "UPDATE devices SET nickname = ? WHERE device_id = ?",
                    (nickname, device_id),
                )

                conn.commit()

                # Force WAL checkpoint to flush changes to main database file
                conn.execute("PRAGMA wal_checkpoint(FULL)")

                logger.info(f"Updated nickname for device {device_id} to '{nickname}'")
                return True

            except Exception as e:
                logger.error(f"Error updating device nickname: {e}")
                return False

    def upsert_collector(
        self,
        collector_id: str,
        display_name: str | None = None,
        version: str | None = None,
        metadata: dict | None = None,
    ) -> bool:
        """Insert or update collector information.

        Args:
            collector_id: Collector identifier
            display_name: Human-readable name
            version: Collector software version
            metadata: Additional metadata as dict

        Returns:
            True if successful
        """
        with self._lock:
            try:
                import json

                conn = self._get_connection()
                cursor = conn.cursor()

                current_time = time.time()
                metadata_json = json.dumps(metadata) if metadata else None

                cursor.execute(
                    """
                    INSERT INTO collectors (collector_id, display_name, version, metadata, first_seen, last_seen, last_heartbeat)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(collector_id) DO UPDATE SET
                        display_name = ?,
                        version = ?,
                        metadata = ?,
                        last_seen = ?
                    """,
                    (
                        collector_id,
                        display_name,
                        version,
                        metadata_json,
                        current_time,
                        current_time,
                        current_time,
                        display_name,
                        version,
                        metadata_json,
                        current_time,
                    ),
                )

                conn.commit()
                logger.debug(f"Upserted collector {collector_id}")
                return True

            except Exception as e:
                logger.error(f"Error upserting collector: {e}")
                return False

    def update_collector_heartbeat(self, collector_id: str) -> bool:
        """Update collector's last heartbeat timestamp.

        Args:
            collector_id: Collector identifier

        Returns:
            True if successful
        """
        with self._lock:
            try:
                conn = self._get_connection()
                cursor = conn.cursor()

                current_time = time.time()
                cursor.execute(
                    "UPDATE collectors SET last_heartbeat = ?, last_seen = ? WHERE collector_id = ?",
                    (current_time, current_time, collector_id),
                )

                conn.commit()
                return cursor.rowcount > 0

            except Exception as e:
                logger.error(f"Error updating collector heartbeat: {e}")
                return False

    def get_all_collectors(self) -> list[dict]:
        """Get all known collectors from database.

        Returns:
            List of collector dictionaries
        """
        with self._lock:
            try:
                import json

                conn = self._get_connection()
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT collector_id, display_name, version, metadata, first_seen, last_seen, last_heartbeat
                    FROM collectors
                    ORDER BY last_seen DESC
                """)

                results = []
                for row in cursor.fetchall():
                    metadata = json.loads(row[3]) if row[3] else {}
                    results.append(
                        {
                            "collector_id": row[0],
                            "display_name": row[1],
                            "version": row[2],
                            "metadata": metadata,
                            "first_seen": row[4],
                            "last_seen": row[5],
                            "last_heartbeat": row[6],
                        }
                    )

                return results

            except Exception as e:
                logger.error(f"Error retrieving collectors: {e}")
                return []

    def upsert_device_collector_mapping(self, device_id: str, collector_id: str) -> bool:
        """Insert or update device-collector mapping.

        Args:
            device_id: Device identifier
            collector_id: Collector identifier

        Returns:
            True if successful
        """
        with self._lock:
            try:
                conn = self._get_connection()
                cursor = conn.cursor()

                current_time = time.time()
                cursor.execute(
                    """
                    INSERT INTO device_collector_mappings (device_id, collector_id, first_associated, last_associated)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(device_id, collector_id) DO UPDATE SET
                        last_associated = ?
                    """,
                    (device_id, collector_id, current_time, current_time, current_time),
                )

                conn.commit()
                return True

            except Exception as e:
                logger.error(f"Error upserting device-collector mapping: {e}")
                return False

    def get_device_collectors(self, device_id: str) -> list[dict]:
        """Get all collectors associated with a device.

        Args:
            device_id: Device identifier

        Returns:
            List of collector information
        """
        with self._lock:
            try:
                import json

                conn = self._get_connection()
                cursor = conn.cursor()

                cursor.execute(
                    """
                    SELECT c.collector_id, c.display_name, c.version, c.metadata,
                           m.first_associated, m.last_associated
                    FROM device_collector_mappings m
                    JOIN collectors c ON m.collector_id = c.collector_id
                    WHERE m.device_id = ?
                    ORDER BY m.last_associated DESC
                    """,
                    (device_id,),
                )

                results = []
                for row in cursor.fetchall():
                    metadata = json.loads(row[3]) if row[3] else {}
                    results.append(
                        {
                            "collector_id": row[0],
                            "display_name": row[1],
                            "version": row[2],
                            "metadata": metadata,
                            "first_associated": row[4],
                            "last_associated": row[5],
                        }
                    )

                return results

            except Exception as e:
                logger.error(f"Error retrieving device collectors: {e}")
                return []

    # Device alignment methods (calibration)

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
        """Save or update device alignment from calibration.

        Args:
            device_id: Device identifier
            time_offset: Computed time offset in seconds
            confidence: Alignment confidence (0-1)
            tap_count: Number of taps used for calibration
            drift: Clock drift multiplier (default 1.0)
            mean_error: Mean alignment error in seconds
            std_error: Standard deviation of alignment error
            offset_version: TimeAlignmentService offset version

        Returns:
            True if successful, False otherwise
        """
        with self._lock:
            try:
                conn = self._get_connection()
                cursor = conn.cursor()

                calibrated_at = time.time()

                cursor.execute(
                    """
                    INSERT INTO device_alignments (
                        device_id, time_offset, drift, confidence, tap_count,
                        mean_error, std_error, calibrated_at, is_valid, offset_version
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                    ON CONFLICT(device_id) DO UPDATE SET
                        time_offset = excluded.time_offset,
                        drift = excluded.drift,
                        confidence = excluded.confidence,
                        tap_count = excluded.tap_count,
                        mean_error = excluded.mean_error,
                        std_error = excluded.std_error,
                        calibrated_at = excluded.calibrated_at,
                        is_valid = 1,
                        offset_version = excluded.offset_version
                    """,
                    (
                        device_id,
                        time_offset,
                        drift,
                        confidence,
                        tap_count,
                        mean_error,
                        std_error,
                        calibrated_at,
                        offset_version,
                    ),
                )

                conn.commit()
                logger.info(f"Saved alignment for device {device_id}")
                return True

            except Exception as e:
                logger.error(f"Error saving device alignment: {e}")
                return False

    def get_device_alignment(self, device_id: str) -> dict[str, object] | None:
        """Get device alignment.

        Args:
            device_id: Device identifier

        Returns:
            Alignment data or None if not found
        """
        with self._lock:
            try:
                conn = self._get_connection()
                cursor = conn.cursor()

                cursor.execute(
                    """
                    SELECT device_id, time_offset, drift, confidence, tap_count,
                           mean_error, std_error, calibrated_at, is_valid, offset_version
                    FROM device_alignments
                    WHERE device_id = ?
                    """,
                    (device_id,),
                )

                row = cursor.fetchone()
                if not row:
                    return None

                return {
                    "device_id": row[0],
                    "time_offset": row[1],
                    "drift": row[2],
                    "confidence": row[3],
                    "tap_count": row[4],
                    "mean_error": row[5],
                    "std_error": row[6],
                    "calibrated_at": row[7],
                    "is_valid": bool(row[8]),
                    "offset_version": row[9],
                }

            except Exception as e:
                logger.error(f"Error getting device alignment: {e}")
                return None

    def get_all_alignments(self, valid_only: bool = False) -> list[dict[str, object]]:
        """Get all device alignments.

        Args:
            valid_only: If True, only return valid alignments

        Returns:
            List of alignment data
        """
        with self._lock:
            try:
                conn = self._get_connection()
                cursor = conn.cursor()

                query = """
                    SELECT device_id, time_offset, drift, confidence, tap_count,
                           mean_error, std_error, calibrated_at, is_valid, offset_version
                    FROM device_alignments
                """

                if valid_only:
                    query += " WHERE is_valid = 1"

                query += " ORDER BY calibrated_at DESC"

                cursor.execute(query)

                results = []
                for row in cursor.fetchall():
                    results.append(
                        {
                            "device_id": row[0],
                            "time_offset": row[1],
                            "drift": row[2],
                            "confidence": row[3],
                            "tap_count": row[4],
                            "mean_error": row[5],
                            "std_error": row[6],
                            "calibrated_at": row[7],
                            "is_valid": bool(row[8]),
                            "offset_version": row[9],
                        }
                    )

                return results

            except Exception as e:
                logger.error(f"Error getting alignments: {e}")
                return []

    def invalidate_device_alignment(self, device_id: str) -> bool:
        """Mark device alignment as invalid (e.g., after device reconnect).

        Args:
            device_id: Device identifier

        Returns:
            True if successful, False otherwise
        """
        with self._lock:
            try:
                conn = self._get_connection()
                cursor = conn.cursor()

                cursor.execute(
                    "UPDATE device_alignments SET is_valid = 0 WHERE device_id = ?",
                    (device_id,),
                )

                conn.commit()

                if cursor.rowcount > 0:
                    logger.info(f"Invalidated alignment for device {device_id}")
                    return True

                return False

            except Exception as e:
                logger.error(f"Error invalidating device alignment: {e}")
                return False

    def delete_device_alignment(self, device_id: str) -> bool:
        """Delete device alignment.

        Args:
            device_id: Device identifier

        Returns:
            True if successful, False otherwise
        """
        with self._lock:
            try:
                conn = self._get_connection()
                cursor = conn.cursor()

                cursor.execute("DELETE FROM device_alignments WHERE device_id = ?", (device_id,))

                conn.commit()

                if cursor.rowcount > 0:
                    logger.info(f"Deleted alignment for device {device_id}")
                    return True

                return False

            except Exception as e:
                logger.error(f"Error deleting device alignment: {e}")
                return False

    def close(self) -> None:
        """Close database connection."""
        with self._lock:
            if self._conn:
                self._conn.close()
                self._conn = None
                logger.info("Database connection closed")
