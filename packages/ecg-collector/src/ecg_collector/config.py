"""Configuration management for ECG Collector."""

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DeviceConfig(BaseSettings):
    """Configuration for a single device."""

    nickname: str | None = Field(
        default=None,
        description="Human-readable nickname for the device",
    )
    esp_id: str | None = Field(
        default=None,
        description="ESP32 ID for USB mode (maps this device to a specific ESP32)",
    )
    ecg_sample_rate: int | None = Field(
        default=None,
        description="ECG sample rate override (Hz), uses global default if not set",
    )
    acc_sample_rate: int | None = Field(
        default=None,
        description="Accelerometer sample rate override (Hz), uses global default if not set",
    )
    ble_adapter: str | None = Field(
        default=None,
        description="Pin device to specific BLE adapter (e.g., 'hci0')",
    )
    enabled: bool = Field(
        default=True,
        description="Enable/disable this device",
    )


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

    model_config = SettingsConfigDict(
        extra="ignore",  # Ignore old fields like allowed_device_ids, device_map
    )

    auto_discover: bool = Field(
        default=True,
        description="Auto-discover USB devices when no devices are specified",
    )
    devices: list[str] = Field(
        default_factory=list,
        description="Explicit USB device paths (e.g., /dev/ttyACM0)",
    )
    ecg_sample_rate: int = Field(
        default=130,
        description="Default ECG sample rate for USB devices (Hz)",
    )
    acc_sample_rate: int = Field(
        default=100,
        description="Default accelerometer sample rate for USB devices (Hz)",
    )
    max_targets_per_esp: int = Field(
        default=1,
        description="Maximum number of Polar devices to assign per ESP",
    )
    persist_config: bool = Field(
        default=True,
        description="Persist USB configuration on device when supported",
    )
    detect_timeout_s: float = Field(
        default=20.0,
        description="Timeout to detect valid USB data before skipping a device",
    )

    @field_validator("max_targets_per_esp", mode="before")
    @classmethod
    def normalize_max_targets_per_esp(cls, v: object) -> int:
        """Clamp max_targets_per_esp to a supported range."""
        if isinstance(v, bool):
            return 1
        if isinstance(v, (int, str, bytes, bytearray)):
            try:
                value = int(v)
            except (TypeError, ValueError):
                return 1
        else:
            return 1
        if value < 1:
            return 1
        if value > 2:
            return 2
        return value


class CollectorSettings(BaseSettings):
    """Main collector configuration."""

    model_config = SettingsConfigDict(
        env_prefix="ECG_COLLECTOR_",
        env_nested_delimiter="__",
        extra="ignore",  # Ignore extra fields for backward compatibility
    )

    collector_id: str = Field(
        default="collector-1",
        description="Unique identifier for this collector",
    )

    display_name: str = Field(
        default="ECG Collector 1",
        description="Human-readable display name for this collector",
    )

    # Unified device configuration (device_id -> config)
    devices: dict[str, DeviceConfig] = Field(
        default_factory=dict,
        description="Device configurations (Polar device ID -> DeviceConfig)",
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

    @field_validator("devices", mode="before")
    @classmethod
    def normalize_devices(cls, v: object) -> dict[str, DeviceConfig]:
        """Normalize devices dict to ensure all values are DeviceConfig instances."""
        if not isinstance(v, dict):
            return {}  # Return empty dict for invalid input

        result: dict[str, DeviceConfig] = {}
        for device_id, config in v.items():
            if isinstance(config, DeviceConfig):
                result[device_id] = config
            elif isinstance(config, dict):
                result[device_id] = DeviceConfig(**config)
            elif config is None:
                # Allow empty device config (use all defaults)
                result[device_id] = DeviceConfig()
            else:
                raise ValueError(f"Invalid device config for {device_id}: {config}")
        return result

    def get_device_list(self) -> list[str]:
        """Get list of all enabled device IDs.

        Returns:
            List of device IDs that are enabled
        """
        return [device_id for device_id, config in self.devices.items() if config.enabled]

    def get_esp_to_device_map(self) -> dict[str, str]:
        """Build ESP ID -> Device ID mapping for USB mode.

        Returns:
            Dictionary mapping ESP IDs to Polar device IDs
        """
        return {
            config.esp_id: device_id
            for device_id, config in self.devices.items()
            if config.esp_id and config.enabled
        }

    def get_device_config(self, device_id: str) -> DeviceConfig | None:
        """Get configuration for a specific device.

        Args:
            device_id: Polar device ID

        Returns:
            DeviceConfig or None if not found
        """
        return self.devices.get(device_id)

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
