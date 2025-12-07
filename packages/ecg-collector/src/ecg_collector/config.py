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


class CollectorSettings(BaseSettings):
    """Main collector configuration."""

    model_config = SettingsConfigDict(
        env_prefix="ECG_COLLECTOR_",
        env_nested_delimiter="__",
        yaml_file="config.yaml",
        extra="ignore",
    )

    collector_id: str = Field(
        default="collector-1",
        description="Unique identifier for this collector",
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
            config_data = yaml.safe_load(f)

        # Extract collector-specific configuration
        collector_config = config_data.get("collector", {})

        return cls(**collector_config)
