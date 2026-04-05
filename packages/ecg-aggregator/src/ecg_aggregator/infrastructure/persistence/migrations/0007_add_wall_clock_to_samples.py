"""
Add wall_clock_us column to ecg_samples and accelerometer_samples tables.

Stores the collector-issued wall clock timestamp (epoch time) when the frame was received.
This provides a third timestamp alongside device_timestamp (polar_clock) and global_time (synced).
"""

from yoyo import step

__depends__ = {"0006_add_device_alignments"}

steps = [
    step(
        "ALTER TABLE ecg_samples ADD COLUMN wall_clock_us INTEGER",
        # SQLite doesn't support DROP COLUMN easily, so rollback is not provided
        None,
    ),
    step(
        "ALTER TABLE accelerometer_samples ADD COLUMN wall_clock_us INTEGER",
        None,
    ),
]
