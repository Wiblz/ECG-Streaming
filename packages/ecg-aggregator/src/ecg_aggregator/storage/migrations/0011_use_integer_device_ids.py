"""
Convert device_id from TEXT to INTEGER foreign key.

This dramatically reduces storage by using 4-byte integers instead of 18+ byte strings
for device references in sample tables. For 2M+ samples, this saves ~30MB and improves
query performance.

Before:
  devices(device_id TEXT PRIMARY KEY, ...)
  ecg_samples(device_id TEXT, ...)

After:
  devices(id INTEGER PRIMARY KEY, device_id TEXT UNIQUE, ...)
  ecg_samples(device_id INTEGER REFERENCES devices(id), ...)
"""

from yoyo import step

__depends__ = {"0010_remove_inserted_at"}

steps = [
    # Step 1: Rename devices table and add integer ID
    step(
        """
        CREATE TABLE devices_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT UNIQUE NOT NULL,
            nickname TEXT,
            first_seen REAL NOT NULL,
            last_seen REAL NOT NULL,
            total_samples INTEGER DEFAULT 0
        )
        """,
        "DROP TABLE devices_new",
    ),
    step(
        """
        INSERT INTO devices_new (device_id, nickname, first_seen, last_seen, total_samples)
        SELECT device_id, nickname, first_seen, last_seen, total_samples
        FROM devices
        """,
        None,
    ),
    step(
        "DROP TABLE devices",
        None,
    ),
    step(
        "ALTER TABLE devices_new RENAME TO devices",
        None,
    ),
    # Step 2: Migrate ecg_samples table
    step(
        """
        CREATE TABLE ecg_samples_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id INTEGER NOT NULL,
            global_time REAL NOT NULL,
            device_timestamp REAL NOT NULL,
            raw_value INTEGER NOT NULL,
            confidence REAL NOT NULL,
            session_id INTEGER,
            wall_clock_us INTEGER,
            receiver_clock_us INTEGER,
            time_verified INTEGER DEFAULT 0,
            FOREIGN KEY (device_id) REFERENCES devices(id)
        )
        """,
        "DROP TABLE ecg_samples_new",
    ),
    step(
        """
        INSERT INTO ecg_samples_new (id, device_id, global_time, device_timestamp, raw_value, confidence, session_id, wall_clock_us, receiver_clock_us, time_verified)
        SELECT
            ecg_samples.id,
            devices.id,
            ecg_samples.global_time,
            ecg_samples.device_timestamp,
            ecg_samples.raw_value,
            ecg_samples.confidence,
            ecg_samples.session_id,
            ecg_samples.wall_clock_us,
            ecg_samples.receiver_clock_us,
            ecg_samples.time_verified
        FROM ecg_samples
        JOIN devices ON ecg_samples.device_id = devices.device_id
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
    step(
        "CREATE INDEX idx_device_time ON ecg_samples (device_id, global_time)",
        "DROP INDEX idx_device_time",
    ),
    step(
        "CREATE INDEX idx_global_time ON ecg_samples (global_time)",
        "DROP INDEX idx_global_time",
    ),
    # Step 3: Migrate accelerometer_samples table
    step(
        """
        CREATE TABLE accelerometer_samples_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id INTEGER NOT NULL,
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
            time_verified INTEGER DEFAULT 0,
            FOREIGN KEY (device_id) REFERENCES devices(id)
        )
        """,
        "DROP TABLE accelerometer_samples_new",
    ),
    step(
        """
        INSERT INTO accelerometer_samples_new (id, device_id, global_time, device_timestamp, x, y, z, confidence, session_id, magnitude, wall_clock_us, receiver_clock_us, time_verified)
        SELECT
            accelerometer_samples.id,
            devices.id,
            accelerometer_samples.global_time,
            accelerometer_samples.device_timestamp,
            accelerometer_samples.x,
            accelerometer_samples.y,
            accelerometer_samples.z,
            accelerometer_samples.confidence,
            accelerometer_samples.session_id,
            accelerometer_samples.magnitude,
            accelerometer_samples.wall_clock_us,
            accelerometer_samples.receiver_clock_us,
            accelerometer_samples.time_verified
        FROM accelerometer_samples
        JOIN devices ON accelerometer_samples.device_id = devices.device_id
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
    step(
        "CREATE INDEX idx_acc_device_time ON accelerometer_samples (device_id, global_time)",
        "DROP INDEX idx_acc_device_time",
    ),
    step(
        "CREATE INDEX idx_acc_global_time ON accelerometer_samples (global_time)",
        "DROP INDEX idx_acc_global_time",
    ),
]
