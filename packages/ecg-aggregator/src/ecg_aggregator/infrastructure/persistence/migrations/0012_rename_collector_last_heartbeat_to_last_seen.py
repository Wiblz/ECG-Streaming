"""Drop collectors.last_heartbeat column.

last_seen already tracks the last activity timestamp and is kept current.
last_heartbeat was never updated after registration, making it redundant.
SQLite does not support DROP COLUMN directly; we recreate the table.
"""

from yoyo import step

__depends__ = {"0011_use_integer_device_ids"}

steps = [
    step(
        """
        CREATE TABLE collectors_new (
            collector_id TEXT PRIMARY KEY,
            display_name TEXT,
            version TEXT,
            metadata TEXT,
            first_seen REAL NOT NULL,
            last_seen REAL NOT NULL
        )
        """,
        "DROP TABLE collectors_new",
    ),
    step(
        """
        INSERT INTO collectors_new
            SELECT collector_id, display_name, version, metadata, first_seen,
                   COALESCE(last_heartbeat, last_seen)
            FROM collectors
        """,
        None,
    ),
    step("DROP TABLE collectors", None),
    step("ALTER TABLE collectors_new RENAME TO collectors", None),
]
