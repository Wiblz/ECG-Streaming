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

        Note:
            Environment variables override YAML values.
            Use ECG_COLLECTOR_* prefix (e.g., ECG_COLLECTOR_AGGREGATOR__HOST).
        """
        import os

        import yaml

        with open(config_path) as f:
            config_data = yaml.safe_load(f) or {}

        # Check which env vars are actually set
        env_prefix = "ECG_COLLECTOR_"
        env_delimiter = "__"

        # Collect env var overrides
        import json
        from typing import Any

        env_overrides: dict[str, Any] = {}
        for env_key, env_value in os.environ.items():
            if env_key.startswith(env_prefix):
                # Remove prefix and convert to nested dict structure
                key_path = env_key[len(env_prefix) :].lower().split(env_delimiter)

                # Try to parse value as JSON for complex types (lists, dicts, bools, numbers)
                # If it fails, keep as string
                try:
                    parsed_value = json.loads(env_value)
                except (json.JSONDecodeError, ValueError):
                    parsed_value = env_value

                # Build nested dict
                current = env_overrides
                for key in key_path[:-1]:
                    if key not in current:
                        current[key] = {}
                    current = current[key]

                # Set the final value
                current[key_path[-1]] = parsed_value

        # Merge: YAML provides base, env_overrides take precedence
        def deep_merge(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
            """Recursively merge overrides into base."""
            result = base.copy()
            for key, value in overrides.items():
                if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                    result[key] = deep_merge(result[key], value)
                else:
                    result[key] = value
            return result

        merged_data = deep_merge(config_data, env_overrides)
        return cls(**merged_data)
