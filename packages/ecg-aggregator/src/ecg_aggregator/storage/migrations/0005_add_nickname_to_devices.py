"""
Add nickname column to devices table.

Allows users to assign friendly names to devices.
"""

from yoyo import step

__depends__ = {"0004_add_magnitude_to_acc_samples"}

steps = [
    step(
        "ALTER TABLE devices ADD COLUMN nickname TEXT",
        # SQLite doesn't support DROP COLUMN easily, so rollback is not provided
        None,
    ),
]
