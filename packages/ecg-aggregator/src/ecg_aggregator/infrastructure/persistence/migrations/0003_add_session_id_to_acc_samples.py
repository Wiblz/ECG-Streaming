"""
Add session_id column to accelerometer_samples table.

This allows accelerometer samples to be associated with recording sessions.
"""

from yoyo import step

__depends__ = {"0002_add_session_id_to_ecg_samples"}

steps = [
    step(
        "ALTER TABLE accelerometer_samples ADD COLUMN session_id INTEGER",
        # SQLite doesn't support DROP COLUMN easily, so rollback is not provided
        None,
    ),
    step(
        "CREATE INDEX idx_acc_session_id ON accelerometer_samples (session_id)",
        "DROP INDEX idx_acc_session_id",
    ),
]
