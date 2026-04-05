"""Device alignment (calibration) persistence."""

import sqlite3
import time
from threading import RLock

from ecg_common.logging import get_logger

logger = get_logger(__name__)


class AlignmentRepository:
    """Read/write access to the device_alignments table."""

    def __init__(self, conn: sqlite3.Connection, lock: RLock) -> None:
        self._conn = conn
        self._lock = lock

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
        """Save or update device alignment from calibration."""
        with self._lock:
            try:
                cursor = self._conn.cursor()
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

                self._conn.commit()
                logger.info(f"Saved alignment for device {device_id}")
                return True

            except Exception as e:
                logger.error(f"Error saving device alignment: {e}")
                return False

    def get_device_alignment(self, device_id: str) -> dict[str, object] | None:
        """Get alignment data for a device."""
        with self._lock:
            try:
                cursor = self._conn.cursor()
                cursor.execute(
                    """
                    SELECT device_id, time_offset, drift, confidence, tap_count,
                           mean_error, std_error, calibrated_at, is_valid, offset_version
                    FROM device_alignments WHERE device_id = ?
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
        """Get all device alignments."""
        with self._lock:
            try:
                cursor = self._conn.cursor()
                query = """
                    SELECT device_id, time_offset, drift, confidence, tap_count,
                           mean_error, std_error, calibrated_at, is_valid, offset_version
                    FROM device_alignments
                """
                if valid_only:
                    query += " WHERE is_valid = 1"
                query += " ORDER BY calibrated_at DESC"

                cursor.execute(query)

                return [
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
                    for row in cursor.fetchall()
                ]

            except Exception as e:
                logger.error(f"Error getting alignments: {e}")
                return []

    def invalidate_device_alignment(self, device_id: str) -> bool:
        """Mark device alignment as invalid."""
        with self._lock:
            try:
                cursor = self._conn.cursor()
                cursor.execute(
                    "UPDATE device_alignments SET is_valid = 0 WHERE device_id = ?", (device_id,)
                )
                self._conn.commit()

                if cursor.rowcount > 0:
                    logger.info(f"Invalidated alignment for device {device_id}")
                    return True
                return False

            except Exception as e:
                logger.error(f"Error invalidating device alignment: {e}")
                return False

    def delete_device_alignment(self, device_id: str) -> bool:
        """Delete device alignment."""
        with self._lock:
            try:
                cursor = self._conn.cursor()
                cursor.execute("DELETE FROM device_alignments WHERE device_id = ?", (device_id,))
                self._conn.commit()

                if cursor.rowcount > 0:
                    logger.info(f"Deleted alignment for device {device_id}")
                    return True
                return False

            except Exception as e:
                logger.error(f"Error deleting device alignment: {e}")
                return False
