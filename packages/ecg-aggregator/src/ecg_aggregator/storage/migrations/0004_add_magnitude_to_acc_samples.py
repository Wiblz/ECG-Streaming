"""
Add magnitude column to accelerometer_samples table.

Pre-calculated magnitude for efficient querying and filtering.
"""

from yoyo import step

__depends__ = {"0003_add_session_id_to_acc_samples"}

steps = [
    step(
        "ALTER TABLE accelerometer_samples ADD COLUMN magnitude REAL",
        # SQLite doesn't support DROP COLUMN easily, so rollback is not provided
        None,
    ),
]
