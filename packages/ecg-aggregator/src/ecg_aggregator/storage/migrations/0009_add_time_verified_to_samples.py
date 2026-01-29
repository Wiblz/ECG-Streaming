"""
Add time_verified column to ecg_samples and accelerometer_samples tables.

Marks samples whose polar_clock_us came directly from PMD frame (last sample in frame)
vs samples with interpolated timestamps (all other samples).
"""

from yoyo import step

__depends__ = {"0008_add_receiver_clock_to_samples"}

steps = [
    step(
        "ALTER TABLE ecg_samples ADD COLUMN time_verified INTEGER DEFAULT 0",
        # SQLite doesn't support DROP COLUMN easily, so rollback is not provided
        None,
    ),
    step(
        "ALTER TABLE accelerometer_samples ADD COLUMN time_verified INTEGER DEFAULT 0",
        None,
    ),
]
