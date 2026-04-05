"""Session persistence."""

import csv
import sqlite3
import time
from pathlib import Path
from threading import RLock

from ecg_common.logging import get_logger

from ecg_aggregator.domain.queries import SessionSortField, SortOrder

logger = get_logger(__name__)


class SessionRepository:
    """Read/write access to the sessions table and session sample queries."""

    def __init__(self, conn: sqlite3.Connection, lock: RLock) -> None:
        self._conn = conn
        self._lock = lock

    def _calculate_session_stats(self, cursor: sqlite3.Cursor, session_id: int) -> tuple[int, int]:
        """Return (sample_count, device_count) for a session."""
        cursor.execute("SELECT COUNT(*) FROM ecg_samples WHERE session_id = ?", (session_id,))
        ecg_count = cursor.fetchone()[0]

        cursor.execute(
            "SELECT COUNT(*) FROM accelerometer_samples WHERE session_id = ?", (session_id,)
        )
        acc_count = cursor.fetchone()[0]

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

        return ecg_count + acc_count, device_count

    def _build_filter_clause(
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

    def _build_order_clause(
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

    def create_session(
        self,
        start_time: float | None = None,
        end_time: float | None = None,
        notes: str | None = None,
    ) -> int:
        """Create a new recording session. Returns session ID or -1 on error."""
        with self._lock:
            try:
                cursor = self._conn.cursor()

                if start_time is None:
                    start_time = time.time()

                cursor.execute(
                    "INSERT INTO sessions (start_time, end_time, notes) VALUES (?, ?, ?)",
                    (start_time, end_time, notes),
                )

                session_id = cursor.lastrowid
                self._conn.commit()

                logger.info(f"Created session {session_id}")
                return session_id if session_id is not None else -1

            except Exception as e:
                logger.error(f"Error creating session: {e}")
                return -1

    def end_session(self, session_id: int, end_time: float | None = None) -> bool:
        """End a recording session by setting its end time."""
        with self._lock:
            try:
                cursor = self._conn.cursor()

                if end_time is None:
                    end_time = time.time()

                cursor.execute("SELECT start_time FROM sessions WHERE id = ?", (session_id,))
                result = cursor.fetchone()
                if not result:
                    logger.error(f"Session {session_id} not found")
                    return False
                start_time = result[0]

                cursor.execute(
                    """
                    UPDATE ecg_samples SET session_id = NULL
                    WHERE session_id = ? AND (global_time < ? OR global_time > ?)
                    """,
                    (session_id, start_time, end_time),
                )
                ecg_cleaned = cursor.rowcount

                cursor.execute(
                    """
                    UPDATE accelerometer_samples SET session_id = NULL
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

                sample_count, device_count = self._calculate_session_stats(cursor, session_id)

                cursor.execute(
                    "UPDATE sessions SET end_time = ?, sample_count = ?, device_count = ? WHERE id = ?",
                    (end_time, sample_count, device_count, session_id),
                )

                self._conn.commit()

                logger.info(
                    f"Ended session {session_id} at {end_time} "
                    f"({sample_count} samples, {device_count} devices)"
                )
                return True

            except Exception as e:
                logger.error(f"Error ending session: {e}")
                return False

    def get_session(self, session_id: int) -> dict | None:
        """Get a single session by ID."""
        with self._lock:
            try:
                cursor = self._conn.cursor()

                cursor.execute(
                    "SELECT id, start_time, end_time, device_count, sample_count, notes FROM sessions WHERE id = ?",
                    (session_id,),
                )
                row = cursor.fetchone()
                if not row:
                    return None

                session_data: dict = {
                    "id": row[0],
                    "start_time": row[1],
                    "end_time": row[2],
                    "device_count": row[3],
                    "sample_count": row[4],
                    "notes": row[5],
                    "duration_seconds": (row[2] - row[1]) if row[2] else None,
                }

                if row[3] is None or row[4] is None:
                    sample_count, device_count = self._calculate_session_stats(cursor, session_id)
                    session_data["sample_count"] = sample_count
                    session_data["device_count"] = device_count

                cursor.execute(
                    "SELECT COUNT(*) FROM ecg_samples WHERE session_id = ?", (session_id,)
                )
                session_data["ecg_sample_count"] = cursor.fetchone()[0]

                cursor.execute(
                    "SELECT COUNT(*) FROM accelerometer_samples WHERE session_id = ?", (session_id,)
                )
                session_data["acc_sample_count"] = cursor.fetchone()[0]

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
                session_data["devices"] = [d[0] for d in cursor.fetchall()]

                return session_data

            except Exception as e:
                logger.error(f"Error retrieving session: {e}")
                return None

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
        """Retrieve a filtered, sorted, paginated list of sessions."""
        with self._lock:
            try:
                cursor = self._conn.cursor()

                where_clause, params = self._build_filter_clause(
                    search=search, active=active, has_notes=has_notes, device_id=device_id
                )
                order_by = self._build_order_clause(sort_by=sort_by, sort_order=sort_order)

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

                session_ids = [row[0] for row in rows]
                placeholders = ",".join("?" * len(session_ids))

                cursor.execute(
                    f"SELECT session_id, COUNT(*) FROM ecg_samples WHERE session_id IN ({placeholders}) GROUP BY session_id",
                    session_ids,
                )
                ecg_counts: dict[int, int] = dict(cursor.fetchall())

                cursor.execute(
                    f"SELECT session_id, COUNT(*) FROM accelerometer_samples WHERE session_id IN ({placeholders}) GROUP BY session_id",
                    session_ids,
                )
                acc_counts: dict[int, int] = dict(cursor.fetchall())

                session_devices: dict[int, list[str]] = {sid: [] for sid in session_ids}
                cursor.execute(
                    f"""
                    SELECT e.session_id, d.device_id
                    FROM ecg_samples e JOIN devices d ON e.device_id = d.id
                    WHERE e.session_id IN ({placeholders})
                    GROUP BY e.session_id, d.device_id
                    UNION
                    SELECT a.session_id, d.device_id
                    FROM accelerometer_samples a JOIN devices d ON a.device_id = d.id
                    WHERE a.session_id IN ({placeholders})
                    GROUP BY a.session_id, d.device_id
                    """,
                    session_ids + session_ids,
                )
                for sid, did in cursor.fetchall():
                    session_devices[sid].append(did)

                results = []
                for row in rows:
                    sid = row[0]
                    ecg_count = ecg_counts.get(sid, 0)
                    acc_count = acc_counts.get(sid, 0)
                    devices_list = session_devices.get(sid, [])

                    session_data: dict = {
                        "id": sid,
                        "start_time": row[1],
                        "end_time": row[2],
                        "notes": row[5],
                        "ecg_sample_count": ecg_count,
                        "acc_sample_count": acc_count,
                        "devices": devices_list,
                        "duration_seconds": (row[2] - row[1]) if row[2] else None,
                    }

                    if row[3] is not None and row[4] is not None:
                        session_data["device_count"] = row[3]
                        session_data["sample_count"] = row[4]
                    else:
                        calculated_sample_count = ecg_count + acc_count
                        calculated_device_count = len(devices_list)
                        session_data["sample_count"] = calculated_sample_count
                        session_data["device_count"] = calculated_device_count

                        cursor.execute(
                            "UPDATE sessions SET device_count = ?, sample_count = ? WHERE id = ?",
                            (calculated_device_count, calculated_sample_count, sid),
                        )
                        self._conn.commit()

                    results.append(session_data)

                return results

            except Exception as e:
                logger.error(f"Error retrieving sessions: {e}")
                return []

    def count_sessions(
        self,
        search: str | None = None,
        active: bool | None = None,
        has_notes: bool | None = None,
        device_id: str | None = None,
    ) -> int:
        """Count sessions matching filters."""
        with self._lock:
            try:
                cursor = self._conn.cursor()
                where_clause, params = self._build_filter_clause(
                    search=search, active=active, has_notes=has_notes, device_id=device_id
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

    def update_session(
        self,
        session_id: int,
        end_time: float | None = None,
        notes: str | None = None,
    ) -> bool:
        """Update session metadata."""
        with self._lock:
            try:
                cursor = self._conn.cursor()

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
                cursor.execute(f"UPDATE sessions SET {', '.join(updates)} WHERE id = ?", params)
                self._conn.commit()
                return True

            except Exception as e:
                logger.error(f"Error updating session: {e}")
                return False

    def delete_session(self, session_id: int) -> bool:
        """Delete a session and unlink its samples."""
        with self._lock:
            try:
                cursor = self._conn.cursor()
                cursor.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
                cursor.execute(
                    "UPDATE ecg_samples SET session_id = NULL WHERE session_id = ?", (session_id,)
                )
                self._conn.commit()
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
        """Get ECG samples for a session."""
        with self._lock:
            try:
                cursor = self._conn.cursor()

                query = """
                    SELECT e.id, d.device_id, e.global_time, e.raw_value, e.confidence,
                           e.wall_clock_us, e.receiver_clock_us, e.device_timestamp, e.time_verified
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

                return [
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
                    for row in cursor.fetchall()
                ]

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
        """Get accelerometer samples for a session."""
        with self._lock:
            try:
                cursor = self._conn.cursor()

                query = """
                    SELECT a.id, d.device_id, a.global_time, a.x, a.y, a.z, a.magnitude,
                           a.confidence, a.wall_clock_us, a.receiver_clock_us, a.device_timestamp, a.time_verified
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

                return [
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
                    for row in cursor.fetchall()
                ]

            except Exception as e:
                logger.error(f"Error retrieving session accelerometer samples: {e}")
                return []

    def export_session_to_csv(self, session_id: int, output_path: Path | str) -> bool:
        """Export a session's ECG samples to CSV format."""
        output_path = Path(output_path)

        with self._lock:
            try:
                session = self.get_session(session_id)
                if not session:
                    logger.error(f"Session {session_id} not found")
                    return False

                samples = self.get_session_samples(session_id=session_id)
                if not samples:
                    logger.warning(f"Session {session_id} has no samples")
                    return False

                with open(output_path, "w", newline="") as csvfile:
                    writer = csv.writer(csvfile)
                    writer.writerow(["# Session Export"])
                    writer.writerow(["# session_id", session_id])
                    writer.writerow(["# start_time", session["start_time"]])
                    writer.writerow(["# end_time", session["end_time"]])
                    writer.writerow(["# duration_seconds", session["duration_seconds"]])
                    writer.writerow(["# sample_count", session["sample_count"]])
                    writer.writerow(["# device_count", session["device_count"]])
                    writer.writerow(["# devices", ",".join(session["devices"])])
                    writer.writerow([])
                    writer.writerow(["device_id", "global_time", "raw_value", "confidence"])
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
        """Import a session from CSV format."""

        input_path = Path(input_path)
        if not input_path.exists():
            logger.error(f"CSV file not found: {input_path}")
            return None

        with self._lock:
            try:
                cursor = self._conn.cursor()

                metadata: dict = {}
                samples_data: list[dict] = []

                with open(input_path, newline="") as csvfile:
                    reader = csv.reader(csvfile)
                    in_metadata = True
                    for row in reader:
                        if not row:
                            continue
                        if row[0].startswith("#"):
                            if len(row) >= 2 and row[0] != "# session_id":
                                metadata[row[0][2:]] = row[1] if len(row) > 1 else None
                            continue
                        if in_metadata and row[0] == "device_id":
                            in_metadata = False
                            continue
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

                start_time_value = metadata.get("start_time")
                start_time = (
                    float(start_time_value)
                    if start_time_value is not None
                    else samples_data[0]["global_time"]
                )
                cursor.execute("INSERT INTO sessions (start_time) VALUES (?)", (start_time,))
                session_id = cursor.lastrowid

                for sample in samples_data:
                    device_id_str = str(sample["device_id"])
                    # Inline device lookup to avoid cross-repo dependency
                    cursor.execute("SELECT id FROM devices WHERE device_id = ?", (device_id_str,))
                    row = cursor.fetchone()
                    if row:
                        device_id_int = row[0]
                    else:
                        current_time = time.time()
                        cursor.execute(
                            "INSERT INTO devices (device_id, first_seen, last_seen, total_samples) VALUES (?, ?, ?, 0)",
                            (device_id_str, current_time, current_time),
                        )
                        device_id_int = cursor.lastrowid

                    cursor.execute(
                        """
                        INSERT INTO ecg_samples
                        (device_id, global_time, device_timestamp, raw_value, confidence, session_id)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            device_id_int,
                            sample["global_time"],
                            sample["global_time"],
                            sample["raw_value"],
                            sample["confidence"],
                            session_id,
                        ),
                    )

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

                self._conn.commit()
                logger.info(
                    f"Imported session {session_id} ({len(samples_data)} samples) from {input_path}"
                )
                return session_id

            except Exception as e:
                logger.error(f"Error importing session from CSV: {e}")
                return None
