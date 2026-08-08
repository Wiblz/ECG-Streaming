"""ECG and accelerometer sample persistence."""

import math
import sqlite3
import time
from threading import RLock

from ecg_common.logging import get_logger

from ecg_aggregator.domain.time import (
    DeviceTimestampUs,
    GlobalTimeSeconds,
    ReceiverClockUs,
    WallClockUs,
)
from ecg_aggregator.infrastructure.persistence.batch_rows import AccBatchRow, ECGBatchRow

logger = get_logger(__name__)


class SampleRepository:
    """Read/write access to ECG and accelerometer sample tables."""

    def __init__(self, conn: sqlite3.Connection, lock: RLock) -> None:
        self._conn = conn
        self._lock = lock

    def _get_or_create_device_id(self, device_id_str: str) -> int:
        """Get or create integer device ID from string device ID."""
        with self._lock:
            try:
                cursor = self._conn.cursor()

                cursor.execute("SELECT id FROM devices WHERE device_id = ?", (device_id_str,))
                row = cursor.fetchone()
                if row:
                    return int(row[0])

                current_time = time.time()
                cursor.execute(
                    """
                    INSERT INTO devices (device_id, first_seen, last_seen, total_samples)
                    VALUES (?, ?, ?, 0)
                    """,
                    (device_id_str, current_time, current_time),
                )
                self._conn.commit()

                lastrowid = cursor.lastrowid
                if lastrowid is None:
                    raise RuntimeError(f"Failed to insert device {device_id_str}")
                return lastrowid

            except Exception as e:
                logger.error(f"Error getting/creating device ID for {device_id_str}: {e}")
                raise

    def ensure_device(self, device_id: str) -> int:
        """Ensure a device exists and return its integer primary key."""
        return self._get_or_create_device_id(device_id)

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
        """Store a single ECG sample."""
        device_id_int = self._get_or_create_device_id(device_id)

        with self._lock:
            try:
                cursor = self._conn.cursor()

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

                self._conn.commit()

            except Exception as e:
                logger.error(f"Error storing sample: {e}")

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
        """Store a single accelerometer sample."""
        device_id_int = self._get_or_create_device_id(device_id)

        if magnitude is None:
            magnitude = math.sqrt(x**2 + y**2 + z**2)

        with self._lock:
            try:
                cursor = self._conn.cursor()

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

                self._conn.commit()

            except Exception as e:
                logger.error(f"Error storing accelerometer sample: {e}")

    def add_ecg_samples_batch(self, samples: list[ECGBatchRow]) -> None:
        """Store multiple ECG samples efficiently."""
        if not samples:
            return

        with self._lock:
            try:
                cursor = self._conn.cursor()

                device_id_map: dict[str, int] = {}
                for sample in samples:
                    if sample.device_id not in device_id_map:
                        device_id_map[sample.device_id] = self._get_or_create_device_id(
                            sample.device_id
                        )

                sample_data = [
                    (
                        device_id_map[sample.device_id],
                        sample.global_time,
                        sample.device_timestamp,
                        sample.raw_value,
                        sample.confidence,
                        sample.session_id,
                        sample.wall_clock_us,
                        sample.receiver_clock_us,
                        1 if sample.time_verified else 0,
                    )
                    for sample in samples
                ]

                cursor.executemany(
                    """
                    INSERT INTO ecg_samples
                    (device_id, global_time, device_timestamp, raw_value, confidence, session_id, wall_clock_us, receiver_clock_us, time_verified)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    sample_data,
                )

                current_time = time.time()
                device_counts: dict[str, int] = {}
                for sample in samples:
                    device_counts[sample.device_id] = device_counts.get(sample.device_id, 0) + 1

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

                self._conn.commit()
                logger.debug(f"Stored {len(samples)} ECG samples in batch")

            except Exception:
                # Propagate so SampleBatchWriter keeps the rows for retry.
                self._conn.rollback()
                raise

    def add_acc_samples_batch(self, samples: list[AccBatchRow]) -> None:
        """Store multiple accelerometer samples efficiently."""
        if not samples:
            return

        with self._lock:
            try:
                cursor = self._conn.cursor()

                device_id_map: dict[str, int] = {}
                for sample in samples:
                    if sample.device_id not in device_id_map:
                        device_id_map[sample.device_id] = self._get_or_create_device_id(
                            sample.device_id
                        )

                sample_data = []
                for sample in samples:
                    magnitude = math.sqrt(sample.x**2 + sample.y**2 + sample.z**2)
                    sample_data.append(
                        (
                            device_id_map[sample.device_id],
                            sample.global_time,
                            sample.device_timestamp,
                            sample.x,
                            sample.y,
                            sample.z,
                            magnitude,
                            sample.confidence,
                            sample.session_id,
                            sample.wall_clock_us,
                            sample.receiver_clock_us,
                            1 if sample.time_verified else 0,
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

                current_time = time.time()
                device_counts: dict[str, int] = {}
                for sample in samples:
                    device_counts[sample.device_id] = device_counts.get(sample.device_id, 0) + 1

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

                self._conn.commit()
                logger.debug(f"Stored {len(samples)} accelerometer samples in batch")

            except Exception:
                self._conn.rollback()
                raise

    def get_stats(self) -> dict:
        """Get sample and device statistics."""
        with self._lock:
            try:
                cursor = self._conn.cursor()

                cursor.execute("SELECT COUNT(*) FROM ecg_samples")
                total_samples = cursor.fetchone()[0]

                cursor.execute("SELECT MIN(global_time), MAX(global_time) FROM ecg_samples")
                time_range = cursor.fetchone()

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
                }

            except Exception as e:
                logger.error(f"Error getting stats: {e}")
                return {}
