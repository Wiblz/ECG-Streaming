"""SQLite persistence layer for ECG samples."""

import sqlite3
import time
from pathlib import Path
from threading import Lock

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
        self._lock = Lock()
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

            conn.commit()

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

    def close(self) -> None:
        """Close database connection."""
        with self._lock:
            if self._conn:
                self._conn.close()
                self._conn = None
                logger.info("Database connection closed")
