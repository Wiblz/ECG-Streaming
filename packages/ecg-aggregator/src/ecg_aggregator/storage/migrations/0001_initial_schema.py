"""
Initial database schema for ECG Aggregator.

Creates all base tables:
- ecg_samples: ECG signal data
- accelerometer_samples: Accelerometer data
- sessions: Recording session metadata
- devices: Device registry and metadata
- collectors: Collector instance registry
- device_collector_mappings: Device-collector relationships
"""

from yoyo import step

steps = [
    # ECG samples table
    step(
        """
        CREATE TABLE ecg_samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            global_time REAL NOT NULL,
            device_timestamp REAL NOT NULL,
            raw_value INTEGER NOT NULL,
            confidence REAL NOT NULL,
            inserted_at REAL NOT NULL
        )
        """,
        "DROP TABLE ecg_samples",
    ),
    # ECG samples indexes
    step(
        "CREATE INDEX idx_device_time ON ecg_samples (device_id, global_time)",
        "DROP INDEX idx_device_time",
    ),
    step(
        "CREATE INDEX idx_global_time ON ecg_samples (global_time)",
        "DROP INDEX idx_global_time",
    ),
    # Accelerometer samples table
    step(
        """
        CREATE TABLE accelerometer_samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            global_time REAL NOT NULL,
            device_timestamp REAL NOT NULL,
            x REAL NOT NULL,
            y REAL NOT NULL,
            z REAL NOT NULL,
            confidence REAL NOT NULL,
            inserted_at REAL NOT NULL
        )
        """,
        "DROP TABLE accelerometer_samples",
    ),
    # Accelerometer samples indexes
    step(
        "CREATE INDEX idx_acc_device_time ON accelerometer_samples (device_id, global_time)",
        "DROP INDEX idx_acc_device_time",
    ),
    step(
        "CREATE INDEX idx_acc_global_time ON accelerometer_samples (global_time)",
        "DROP INDEX idx_acc_global_time",
    ),
    # Sessions table
    step(
        """
        CREATE TABLE sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            start_time REAL NOT NULL,
            end_time REAL,
            device_count INTEGER,
            sample_count INTEGER DEFAULT 0,
            notes TEXT
        )
        """,
        "DROP TABLE sessions",
    ),
    # Devices table
    step(
        """
        CREATE TABLE devices (
            device_id TEXT PRIMARY KEY,
            first_seen REAL NOT NULL,
            last_seen REAL NOT NULL,
            total_samples INTEGER DEFAULT 0
        )
        """,
        "DROP TABLE devices",
    ),
    # Collectors table
    step(
        """
        CREATE TABLE collectors (
            collector_id TEXT PRIMARY KEY,
            display_name TEXT,
            version TEXT,
            metadata TEXT,
            first_seen REAL NOT NULL,
            last_seen REAL NOT NULL,
            last_heartbeat REAL
        )
        """,
        "DROP TABLE collectors",
    ),
    # Device-collector mappings table
    step(
        """
        CREATE TABLE device_collector_mappings (
            device_id TEXT NOT NULL,
            collector_id TEXT NOT NULL,
            first_associated REAL NOT NULL,
            last_associated REAL NOT NULL,
            PRIMARY KEY (device_id, collector_id),
            FOREIGN KEY (device_id) REFERENCES devices(device_id),
            FOREIGN KEY (collector_id) REFERENCES collectors(collector_id)
        )
        """,
        "DROP TABLE device_collector_mappings",
    ),
]
