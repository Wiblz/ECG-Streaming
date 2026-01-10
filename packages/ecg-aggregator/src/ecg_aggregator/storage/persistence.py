"""SQLite persistence layer for ECG samples."""

import csv
import sqlite3
import time
from pathlib import Path
from threading import RLock

from ecg_common.logging import get_logger

logger = get_logger(__name__)


class ECGDatabase:
    """SQLite database for storing ECG samples."""

    def __init__(self, db_path: Path | str = "ecg_data.db"):
        """Initialize the database.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self._lock = RLock()
        self._conn: sqlite3.Connection | None = None

        # Create database and tables
        self._init_db()

        logger.info(f"Initialized ECG database at {self.db_path}")

    def _init_db(self) -> None:
        """Initialize database schema."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Main samples table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ecg_samples (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL,
                    global_time REAL NOT NULL,
                    device_timestamp REAL NOT NULL,
                    raw_value INTEGER NOT NULL,
                    confidence REAL NOT NULL,
                    inserted_at REAL NOT NULL
                )
            """)

            # Create indexes separately
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_device_time ON ecg_samples (device_id, global_time)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_global_time ON ecg_samples (global_time)
            """)

            # Session tracking table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    start_time REAL NOT NULL,
                    end_time REAL,
                    device_count INTEGER,
                    sample_count INTEGER DEFAULT 0,
                    notes TEXT
                )
            """)

            # Device metadata table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS devices (
                    device_id TEXT PRIMARY KEY,
                    first_seen REAL NOT NULL,
                    last_seen REAL NOT NULL,
                    total_samples INTEGER DEFAULT 0
                )
            """)

            # Collector registry table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS collectors (
                    collector_id TEXT PRIMARY KEY,
                    display_name TEXT,
                    version TEXT,
                    metadata TEXT,
                    first_seen REAL NOT NULL,
                    last_seen REAL NOT NULL,
                    last_heartbeat REAL
                )
            """)

            # Device-collector mappings table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS device_collector_mappings (
                    device_id TEXT NOT NULL,
                    collector_id TEXT NOT NULL,
                    first_associated REAL NOT NULL,
                    last_associated REAL NOT NULL,
                    PRIMARY KEY (device_id, collector_id),
                    FOREIGN KEY (device_id) REFERENCES devices(device_id),
                    FOREIGN KEY (collector_id) REFERENCES collectors(collector_id)
                )
            """)

            conn.commit()

            # Migrate schema if needed
            self._migrate_schema()

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

    def _migrate_schema(self) -> None:
        """Migrate database schema to latest version."""
        with self._lock:
            try:
                conn = self._get_connection()
                cursor = conn.cursor()

                # Check if session_id column exists in ecg_samples
                cursor.execute("PRAGMA table_info(ecg_samples)")
                columns = [row[1] for row in cursor.fetchall()]

                if "session_id" not in columns:
                    logger.info("Adding session_id column to ecg_samples table")
                    cursor.execute("ALTER TABLE ecg_samples ADD COLUMN session_id INTEGER")
                    cursor.execute(
                        "CREATE INDEX IF NOT EXISTS idx_session_id ON ecg_samples (session_id)"
                    )
                    conn.commit()
                    logger.info("Added session_id column to ecg_samples")

                # Check if nickname column exists in devices
                cursor.execute("PRAGMA table_info(devices)")
                device_columns = [row[1] for row in cursor.fetchall()]

                if "nickname" not in device_columns:
                    logger.info("Adding nickname column to devices table")
                    cursor.execute("ALTER TABLE devices ADD COLUMN nickname TEXT")
                    conn.commit()
                    logger.info("Added nickname column to devices")

            except Exception as e:
                logger.error(f"Error during schema migration: {e}")

    def add_sample(
        self,
        device_id: str,
        global_time: float,
        device_timestamp: float,
        raw_value: int,
        confidence: float,
    ) -> None:
        """Store a single ECG sample.

        Args:
            device_id: Device identifier
            global_time: Synchronized global timestamp
            device_timestamp: Original device timestamp
            raw_value: Raw ECG value
            confidence: Time sync confidence (0-1)
        """
        with self._lock:
            try:
                conn = self._get_connection()
                cursor = conn.cursor()

                cursor.execute(
                    """
                    INSERT INTO ecg_samples
                    (device_id, global_time, device_timestamp, raw_value, confidence, inserted_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (device_id, global_time, device_timestamp, raw_value, confidence, time.time()),
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

    def add_samples_batch(
        self,
        samples: list[tuple[str, float, float, int, float]],
    ) -> None:
        """Store multiple ECG samples efficiently.

        Args:
            samples: List of tuples (device_id, global_time, device_timestamp, raw_value, confidence)
        """
        if not samples:
            return

        with self._lock:
            try:
                conn = self._get_connection()
                cursor = conn.cursor()

                # Prepare batch data
                insert_time = time.time()
                sample_data = [
                    (device_id, global_time, device_timestamp, raw_value, confidence, insert_time)
                    for device_id, global_time, device_timestamp, raw_value, confidence in samples
                ]

                cursor.executemany(
                    """
                    INSERT INTO ecg_samples
                    (device_id, global_time, device_timestamp, raw_value, confidence, inserted_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    sample_data,
                )

                # Update device metadata for each unique device
                device_counts: dict[str, int] = {}
                for device_id, _, _, _, _ in samples:
                    device_counts[device_id] = device_counts.get(device_id, 0) + 1

                for device_id, count in device_counts.items():
                    cursor.execute(
                        """
                        INSERT INTO devices (device_id, first_seen, last_seen, total_samples)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(device_id) DO UPDATE SET
                            last_seen = ?,
                            total_samples = total_samples + ?
                        """,
                        (device_id, insert_time, insert_time, count, insert_time, count),
                    )

                conn.commit()
                logger.debug(f"Stored {len(samples)} samples in batch")

            except Exception as e:
                logger.error(f"Error storing batch: {e}")

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

                query = "SELECT device_id, global_time, device_timestamp, raw_value, confidence FROM ecg_samples WHERE 1=1"
                params: list[str | float | int] = []

                if device_id:
                    query += " AND device_id = ?"
                    params.append(device_id)

                if start_time:
                    query += " AND global_time >= ?"
                    params.append(start_time)

                if end_time:
                    query += " AND global_time <= ?"
                    params.append(end_time)

                query += " ORDER BY global_time ASC"

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
        start_time: float,
        end_time: float | None = None,
        notes: str | None = None,
    ) -> int:
        """Create a new recording session.

        Args:
            start_time: Session start timestamp
            end_time: Session end timestamp (optional)
            notes: Session notes (optional)

        Returns:
            Session ID
        """
        with self._lock:
            try:
                conn = self._get_connection()
                cursor = conn.cursor()

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

    def get_sessions(
        self,
        limit: int | None = None,
        offset: int = 0,
        order_by: str = "start_time DESC",
    ) -> list[dict]:
        """Retrieve all sessions.

        Args:
            limit: Maximum number of sessions to return
            offset: Number of sessions to skip
            order_by: Order clause (default: newest first)

        Returns:
            List of session dictionaries
        """
        with self._lock:
            try:
                conn = self._get_connection()
                cursor = conn.cursor()

                query = "SELECT id, start_time, end_time, device_count, sample_count, notes FROM sessions"
                query += f" ORDER BY {order_by}"

                params: list[int] = []
                if limit:
                    query += " LIMIT ? OFFSET ?"
                    params.extend([limit, offset])

                cursor.execute(query, params)

                results = []
                for row in cursor.fetchall():
                    session_data = {
                        "id": row[0],
                        "start_time": row[1],
                        "end_time": row[2],
                        "device_count": row[3],
                        "sample_count": row[4],
                        "notes": row[5],
                    }

                    # Calculate duration
                    if row[2]:  # end_time
                        session_data["duration_seconds"] = row[2] - row[1]
                    else:
                        session_data["duration_seconds"] = None

                    # Get unique devices for this session
                    cursor.execute(
                        """
                        SELECT DISTINCT device_id FROM ecg_samples
                        WHERE session_id = ?
                        """,
                        (row[0],),
                    )
                    devices = [d[0] for d in cursor.fetchall()]
                    session_data["devices"] = devices

                    results.append(session_data)

                return results

            except Exception as e:
                logger.error(f"Error retrieving sessions: {e}")
                return []

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

                # Get unique devices
                cursor.execute(
                    """
                    SELECT DISTINCT device_id FROM ecg_samples
                    WHERE session_id = ?
                    """,
                    (session_id,),
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
                    SELECT device_id, global_time, raw_value, confidence
                    FROM ecg_samples
                    WHERE session_id = ?
                """
                params: list[int | str | float] = [session_id]

                if device_id:
                    query += " AND device_id = ?"
                    params.append(device_id)

                if start_time is not None:
                    query += " AND global_time >= ?"
                    params.append(start_time)

                if end_time is not None:
                    query += " AND global_time <= ?"
                    params.append(end_time)

                query += " ORDER BY global_time ASC"

                if limit:
                    query += " LIMIT ? OFFSET ?"
                    params.extend([limit, offset])

                cursor.execute(query, params)

                results = []
                for row in cursor.fetchall():
                    results.append(
                        {
                            "device_id": row[0],
                            "global_time": row[1],
                            "raw_value": row[2],
                            "confidence": row[3],
                        }
                    )

                return results

            except Exception as e:
                logger.error(f"Error retrieving session samples: {e}")
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
                current_time = time.time()
                for sample in samples_data:
                    cursor.execute(
                        """
                        INSERT INTO ecg_samples (device_id, global_time, device_timestamp, raw_value, confidence, session_id, inserted_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            sample["device_id"],
                            sample["global_time"],
                            sample[
                                "global_time"
                            ],  # Use global_time as device_timestamp for imported data
                            sample["raw_value"],
                            sample["confidence"],
                            session_id,
                            current_time,
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

    def get_all_devices(self) -> list[dict]:
        """Get all known devices from database.

        Returns:
            List of device dictionaries with metadata
        """
        with self._lock:
            try:
                conn = self._get_connection()
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT device_id, first_seen, last_seen, total_samples, nickname
                    FROM devices
                    ORDER BY last_seen DESC
                """)

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

    def update_device_nickname(self, device_id: str, nickname: str | None) -> bool:
        """Update a device's nickname.

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

                cursor.execute(
                    "UPDATE devices SET nickname = ? WHERE device_id = ?",
                    (nickname, device_id),
                )

                conn.commit()

                if cursor.rowcount > 0:
                    logger.info(f"Updated nickname for device {device_id} to '{nickname}'")
                    return True
                else:
                    logger.warning(f"Device {device_id} not found in database")
                    return False

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

    def close(self) -> None:
        """Close database connection."""
        with self._lock:
            if self._conn:
                self._conn.close()
                self._conn = None
                logger.info("Database connection closed")
