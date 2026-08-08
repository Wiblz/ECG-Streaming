"""
Restore session_id indexes on sample tables.

Migration 0011 rebuilt ecg_samples and accelerometer_samples but only
recreated the device/global time indexes, so the session_id indexes from
migrations 0002/0003 were lost with the dropped tables, turning session
queries into full table scans. IF NOT EXISTS keeps this migration safe on
databases where the indexes still exist.
"""

from yoyo import step

__depends__ = {"0012_rename_collector_last_heartbeat_to_last_seen"}

steps = [
    step(
        "CREATE INDEX IF NOT EXISTS idx_session_id ON ecg_samples (session_id)",
        "DROP INDEX IF EXISTS idx_session_id",
    ),
    step(
        "CREATE INDEX IF NOT EXISTS idx_acc_session_id ON accelerometer_samples (session_id)",
        "DROP INDEX IF EXISTS idx_acc_session_id",
    ),
]
