"""
Add session_id column to ecg_samples table.

This allows ECG samples to be associated with recording sessions.
"""

from yoyo import step

__depends__ = {"0001_initial_schema"}

steps = [
    step(
        "ALTER TABLE ecg_samples ADD COLUMN session_id INTEGER",
        # SQLite doesn't support DROP COLUMN easily, so rollback is not provided
        None,
    ),
    step(
        "CREATE INDEX idx_session_id ON ecg_samples (session_id)",
        "DROP INDEX idx_session_id",
    ),
]
