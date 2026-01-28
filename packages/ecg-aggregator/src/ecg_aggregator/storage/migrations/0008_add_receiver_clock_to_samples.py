"""
Add receiver_clock_us column to ecg_samples and accelerometer_samples tables.

Stores the receiver device clock timestamp (microseconds since ESP32/collector boot).
This provides ESP-specific timing alongside polar_clock_us and wall_clock_us.
"""

from yoyo import step

__depends__ = {"0007_add_wall_clock_to_samples"}

steps = [
    step(
        "ALTER TABLE ecg_samples ADD COLUMN receiver_clock_us INTEGER",
        # SQLite doesn't support DROP COLUMN easily, so rollback is not provided
        None,
    ),
    step(
        "ALTER TABLE accelerometer_samples ADD COLUMN receiver_clock_us INTEGER",
        None,
    ),
]
