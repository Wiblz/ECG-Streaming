"""
Add device_alignments table for calibration-based time synchronization.

Stores computed time alignments from calibration sessions.
Alignments are invalidated when devices reconnect.
"""

from yoyo import step

steps = [
    # Device alignments table
    step(
        """
        CREATE TABLE device_alignments (
            device_id TEXT PRIMARY KEY,
            time_offset REAL NOT NULL,
            drift REAL NOT NULL DEFAULT 1.0,
            confidence REAL NOT NULL,
            tap_count INTEGER NOT NULL,
            mean_error REAL,
            std_error REAL,
            calibrated_at REAL NOT NULL,
            is_valid INTEGER NOT NULL DEFAULT 1,
            offset_version INTEGER
        )
        """,
        "DROP TABLE device_alignments",
    ),
    step(
        "CREATE INDEX idx_alignment_valid ON device_alignments (is_valid, calibrated_at)",
        "DROP INDEX idx_alignment_valid",
    ),
]
