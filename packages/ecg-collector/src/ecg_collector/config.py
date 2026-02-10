"""Configuration management for ECG Collector."""

from pathlib import Path
from typing import cast

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_settings.sources.base import PydanticBaseSettingsSource
from pydantic_settings.sources.providers.yaml import YamlConfigSettingsSource


class DeviceConfig(BaseModel):
    """Configuration for a single device."""

    model_config = ConfigDict(extra="forbid", frozen=True)

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


class BLEConfig(BaseModel):
    """BLE connection configuration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_devices_per_adapter: int = Field(
        default=7,
        description="Maximum number of devices per BLE adapter",
    )
    connection_timeout: int = Field(
        default=10,
        description="Connection timeout in seconds",
    )


class AggregatorConfig(BaseModel):
    """Aggregator connection configuration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

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


class LoggingConfig(BaseModel):
    """Logging configuration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

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


class USBConfig(BaseModel):
    """USB collector configuration."""

    model_config = ConfigDict(
        extra="ignore",  # Ignore old fields like allowed_device_ids, device_map
        frozen=True,
    )

    ecg_sample_rate: int = Field(
        default=130,
        description="Default ECG sample rate for USB devices (Hz)",
    )
    acc_sample_rate: int = Field(
        default=100,
        description="Default accelerometer sample rate for USB devices (Hz)",
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
        extra="forbid",
        frozen=True,
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

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            YamlConfigSettingsSource(settings_cls),
            file_secret_settings,
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

        settings_type = type(
            f"{cls.__name__}WithYaml",
            (cls,),
            {"model_config": cls.model_config | {"yaml_file": config_path}},
        )
        return cast("CollectorSettings", settings_type())
