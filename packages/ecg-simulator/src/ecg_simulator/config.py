"""Configuration dataclasses for the ECG simulator."""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class DeviceStats:
    """Runtime counters for a single device."""

    ecg_samples_sent: int = 0
    acc_samples_sent: int = 0
    status_sent: bool = False


@dataclass(slots=True)
class SimulatedDevice:
    """Synthetic device definition."""

    device_id: str
    nickname: str
    ecg_phase: float
    acc_phase: float
    battery_level: int
    polar_clock_us: int  # Single shared polar clock for the device
    receiver_clock_offset_us: int
    stats: DeviceStats = field(default_factory=DeviceStats)


@dataclass(slots=True)
class SimulatorConfig:
    """Top-level synthetic simulation configuration."""

    host: str
    port: int
    collectors: int
    devices: int
    ecg_rate: int
    acc_rate: int
    batch_size: int
    connect_timeout: float
    heartbeat_interval: float
    report_interval: float
    include_acc: bool
    startup_stagger_ms: int
    duration: float | None
    verbose_sync: bool


@dataclass(slots=True)
class ReplayDevice:
    """Device reconstructed from a recorded session."""

    device_id: str  # original string id e.g. "SIM_AA:BB:CC:DD:EE:FF"
    db_device_id: int  # integer FK in the DB
    nickname: str
    ecg_samples: list  # list of sqlite3.Row
    acc_samples: list  # list of sqlite3.Row
    stats: DeviceStats = field(default_factory=DeviceStats)


@dataclass(slots=True)
class ReplayConfig:
    """Configuration for replay mode."""

    host: str
    port: int
    db_path: Path
    session_id: int
    batch_size: int
    speed: float
    connect_timeout: float
    heartbeat_interval: float
    report_interval: float
    loop: bool
