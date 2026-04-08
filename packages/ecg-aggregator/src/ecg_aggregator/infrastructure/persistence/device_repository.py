"""Device and collector persistence."""

import json
import sqlite3
import time
from threading import RLock

from ecg_common.logging import get_logger

logger = get_logger(__name__)


class DeviceRepository:
    """Read/write access to the devices, collectors, and device_collector_mappings tables."""

    def __init__(self, conn: sqlite3.Connection, lock: RLock) -> None:
        self._conn = conn
        self._lock = lock

    def get_all_devices(self, limit: int | None = None, offset: int = 0) -> list[dict]:
        """Get all known devices."""
        with self._lock:
            try:
                cursor = self._conn.cursor()

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

                return [
                    {
                        "device_id": row[0],
                        "first_seen": row[1],
                        "last_seen": row[2],
                        "total_samples": row[3],
                        "nickname": row[4],
                    }
                    for row in cursor.fetchall()
                ]

            except Exception as e:
                logger.error(f"Error retrieving devices: {e}")
                return []

    def count_devices(self) -> int:
        """Count all known devices."""
        with self._lock:
            try:
                cursor = self._conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM devices")
                row = cursor.fetchone()
                return int(row[0]) if row else 0
            except Exception as e:
                logger.error(f"Error counting devices: {e}")
                return 0

    def update_device_nickname(self, device_id: str, nickname: str | None) -> bool:
        """Update a device's nickname, creating the device entry if needed."""
        with self._lock:
            try:
                cursor = self._conn.cursor()
                current_time = time.time()

                cursor.execute(
                    """
                    INSERT INTO devices (device_id, first_seen, last_seen, total_samples)
                    VALUES (?, ?, ?, 0)
                    ON CONFLICT(device_id) DO NOTHING
                    """,
                    (device_id, current_time, current_time),
                )
                cursor.execute(
                    "UPDATE devices SET nickname = ? WHERE device_id = ?",
                    (nickname, device_id),
                )

                self._conn.commit()
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
        """Insert or update collector information."""
        with self._lock:
            try:
                cursor = self._conn.cursor()
                current_time = time.time()
                metadata_json = json.dumps(metadata) if metadata else None

                cursor.execute(
                    """
                    INSERT INTO collectors (collector_id, display_name, version, metadata, first_seen, last_seen)
                    VALUES (?, ?, ?, ?, ?, ?)
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
                        display_name,
                        version,
                        metadata_json,
                        current_time,
                    ),
                )

                self._conn.commit()
                logger.debug(f"Upserted collector {collector_id}")
                return True

            except Exception as e:
                logger.error(f"Error upserting collector: {e}")
                return False

    def update_collector_last_seen(self, collector_id: str) -> bool:
        """Update collector's last_seen timestamp."""
        with self._lock:
            try:
                cursor = self._conn.cursor()
                cursor.execute(
                    "UPDATE collectors SET last_seen = ? WHERE collector_id = ?",
                    (time.time(), collector_id),
                )
                self._conn.commit()
                return cursor.rowcount > 0

            except Exception as e:
                logger.error(f"Error updating collector last_seen: {e}")
                return False

    def get_all_collectors(self) -> list[dict]:
        """Get all known collectors."""
        with self._lock:
            try:
                cursor = self._conn.cursor()
                cursor.execute("""
                    SELECT collector_id, display_name, version, metadata, first_seen, last_seen
                    FROM collectors
                    ORDER BY last_seen DESC
                """)

                return [
                    {
                        "collector_id": row[0],
                        "display_name": row[1],
                        "version": row[2],
                        "metadata": json.loads(row[3]) if row[3] else {},
                        "first_seen": row[4],
                        "last_seen": row[5],
                    }
                    for row in cursor.fetchall()
                ]

            except Exception as e:
                logger.error(f"Error retrieving collectors: {e}")
                return []

    def upsert_device_collector_mapping(self, device_id: str, collector_id: str) -> bool:
        """Insert or update device-collector mapping."""
        with self._lock:
            try:
                cursor = self._conn.cursor()
                current_time = time.time()
                cursor.execute(
                    """
                    INSERT INTO device_collector_mappings (device_id, collector_id, first_associated, last_associated)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(device_id, collector_id) DO UPDATE SET last_associated = ?
                    """,
                    (device_id, collector_id, current_time, current_time, current_time),
                )
                self._conn.commit()
                return True

            except Exception as e:
                logger.error(f"Error upserting device-collector mapping: {e}")
                return False

    def get_device_collectors(self, device_id: str) -> list[dict]:
        """Get all collectors associated with a device."""
        with self._lock:
            try:
                cursor = self._conn.cursor()
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

                return [
                    {
                        "collector_id": row[0],
                        "display_name": row[1],
                        "version": row[2],
                        "metadata": json.loads(row[3]) if row[3] else {},
                        "first_associated": row[4],
                        "last_associated": row[5],
                    }
                    for row in cursor.fetchall()
                ]

            except Exception as e:
                logger.error(f"Error retrieving device collectors: {e}")
                return []
