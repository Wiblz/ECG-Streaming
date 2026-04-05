"""
Remove unused inserted_at column from sample tables.

The inserted_at column was never queried or used - it only tracked when
samples were written to the database but this information is not needed.
"""

from yoyo import step

__depends__ = {"0009_add_time_verified_to_samples"}

steps = [
    # SQLite doesn't support DROP COLUMN directly, so we need to recreate tables
    # For ecg_samples
    step(
        """
        CREATE TABLE ecg_samples_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            global_time REAL NOT NULL,
            device_timestamp REAL NOT NULL,
            raw_value INTEGER NOT NULL,
            confidence REAL NOT NULL,
            session_id INTEGER,
            wall_clock_us INTEGER,
            receiver_clock_us INTEGER,
            time_verified INTEGER DEFAULT 0
        )
        """,
        "DROP TABLE ecg_samples_new",
    ),
    step(
        "CREATE INDEX idx_device_time_new ON ecg_samples_new (device_id, global_time)",
        "DROP INDEX idx_device_time_new",
    ),
    step(
        "CREATE INDEX idx_global_time_new ON ecg_samples_new (global_time)",
        "DROP INDEX idx_global_time_new",
    ),
    step(
        """
        INSERT INTO ecg_samples_new (id, device_id, global_time, device_timestamp, raw_value, confidence, session_id, wall_clock_us, receiver_clock_us, time_verified)
        SELECT id, device_id, global_time, device_timestamp, raw_value, confidence, session_id, wall_clock_us, receiver_clock_us, time_verified
        FROM ecg_samples
        """,
        None,
    ),
    step(
        "DROP TABLE ecg_samples",
        None,
    ),
    step(
        "ALTER TABLE ecg_samples_new RENAME TO ecg_samples",
        None,
    ),
    # For accelerometer_samples
    step(
        """
        CREATE TABLE accelerometer_samples_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            global_time REAL NOT NULL,
            device_timestamp REAL NOT NULL,
            x REAL NOT NULL,
            y REAL NOT NULL,
            z REAL NOT NULL,
            confidence REAL NOT NULL,
            session_id INTEGER,
            magnitude REAL,
            wall_clock_us INTEGER,
            receiver_clock_us INTEGER,
            time_verified INTEGER DEFAULT 0
        )
        """,
        "DROP TABLE accelerometer_samples_new",
    ),
    step(
        "CREATE INDEX idx_acc_device_time_new ON accelerometer_samples_new (device_id, global_time)",
        "DROP INDEX idx_acc_device_time_new",
    ),
    step(
        "CREATE INDEX idx_acc_global_time_new ON accelerometer_samples_new (global_time)",
        "DROP INDEX idx_acc_global_time_new",
    ),
    step(
        """
        INSERT INTO accelerometer_samples_new (id, device_id, global_time, device_timestamp, x, y, z, confidence, session_id, magnitude, wall_clock_us, receiver_clock_us, time_verified)
        SELECT id, device_id, global_time, device_timestamp, x, y, z, confidence, session_id, magnitude, wall_clock_us, receiver_clock_us, time_verified
        FROM accelerometer_samples
        """,
        None,
    ),
    step(
        "DROP TABLE accelerometer_samples",
        None,
    ),
    step(
        "ALTER TABLE accelerometer_samples_new RENAME TO accelerometer_samples",
        None,
    ),
]
