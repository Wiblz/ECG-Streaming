"""Configuration management for ECG Collector."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class BLEConfig(BaseSettings):
    """BLE connection configuration."""

    max_devices_per_adapter: int = Field(
        default=7,
        description="Maximum number of devices per BLE adapter",
    )
    connection_timeout: int = Field(
        default=10,
        description="Connection timeout in seconds",
    )


class AggregatorConfig(BaseSettings):
    """Aggregator connection configuration."""

    host: str = Field(
        default="localhost",
        description="Aggregator server hostname or IP",
    )
    port: int = Field(
        default=50051,
        description="Aggregator server gRPC port",
    )
    batch_size: int = Field(
        default=50,
        description="Number of samples per batch",
    )
    batch_interval: float = Field(
        default=0.1,
        description="Interval between batch sends (seconds)",
    )


class LoggingConfig(BaseSettings):
    """Logging configuration."""

    level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    )
    format: str = Field(
        default="detailed",
        description="Log format style (simple or detailed)",
    )
    file: Path | None = Field(
        default=None,
        description="Optional log file path",
    )
    ble_debug_file: Path | None = Field(
        default=None,
        description="Optional log file path for BLE debug messages",
    )


class USBConfig(BaseSettings):
    """USB collector configuration."""

    auto_discover: bool = Field(
        default=True,
        description="Auto-discover USB devices when no devices are specified",
    )
    devices: list[str] = Field(
        default_factory=list,
        description="Explicit USB device paths (e.g., /dev/ttyACM0)",
    )
    allowed_device_ids: list[str] = Field(
        default_factory=list,
        description="Optional allowlist of device IDs (empty allows all)",
    )
    device_map: dict[str, str | dict[str, object]] = Field(
        default_factory=dict,
        description=(
            "Mapping of esp_id to Polar device ID (string) or dict with overrides "
            "(device_id, ecg_sample_rate, acc_sample_rate)"
        ),
    )
    ecg_sample_rate: int = Field(
        default=130,
        description="ECG sample rate to configure on USB devices (Hz)",
    )
    acc_sample_rate: int = Field(
        default=100,
        description="Accelerometer sample rate to configure on USB devices (Hz)",
    )
    persist_config: bool = Field(
        default=True,
        description="Persist USB configuration on device when supported",
    )
    detect_timeout_s: float = Field(
        default=20.0,
        description="Timeout to detect valid USB data before skipping a device",
    )


class CollectorSettings(BaseSettings):
    """Main collector configuration."""

    model_config = SettingsConfigDict(
        env_prefix="ECG_COLLECTOR_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    collector_id: str = Field(
        default="collector-1",
        description="Unique identifier for this collector",
    )

    display_name: str = Field(
        default="ECG Collector 1",
        description="Human-readable display name for this collector",
    )

    device_ids: list[str] = Field(
        default_factory=list,
        description="List of device IDs to connect to",
    )

    ble: BLEConfig = Field(
        default_factory=BLEConfig,
        description="BLE connection settings",
    )

    aggregator: AggregatorConfig = Field(
        default_factory=AggregatorConfig,
        description="Aggregator connection settings",
    )

    logging: LoggingConfig = Field(
        default_factory=LoggingConfig,
        description="Logging configuration",
    )

    usb: USBConfig = Field(
        default_factory=USBConfig,
        description="USB collector settings",
    )

    @classmethod
    def from_yaml(cls, config_path: Path) -> CollectorSettings:
        """Load configuration from a YAML file.

        Args:
            config_path: Path to the YAML configuration file

        Returns:
            CollectorSettings instance
        """
        import yaml

        with open(config_path) as f:
            config_data = yaml.safe_load(f) or {}

        return cls(**config_data)
