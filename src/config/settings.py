"""Configuration management for ECG Streaming application."""

from pathlib import Path

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class BLEConfig(BaseModel):
    """BLE adapter configuration."""

    max_devices_per_adapter: int = Field(default=7, ge=1)
    connection_timeout: float = Field(default=10.0, gt=0)
    reconnection_attempts: int = Field(default=3, ge=0)
    scan_duration: float = Field(default=5.0, gt=0)


class SyncConfig(BaseModel):
    """Time synchronization configuration."""

    regression_window_size: int = Field(default=100, ge=10)
    min_samples_for_sync: int = Field(default=20, ge=5)
    confidence_threshold: float = Field(default=0.9, ge=0.0, le=1.0)
    max_drift_ppm: float = Field(default=100.0, gt=0)


class APIConfig(BaseModel):
    """API server configuration."""

    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000, ge=1024, le=65535)
    buffer_duration_seconds: int = Field(default=30, ge=1)
    websocket_fps: int = Field(default=30, ge=1, le=120)
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])


class LoggingConfig(BaseModel):
    """Logging configuration."""

    level: str = Field(default="INFO")
    format: str = Field(default="detailed")
    log_file: Path | None = None


class Settings(BaseSettings):
    """Application settings."""

    # Component configurations
    ble: BLEConfig = Field(default_factory=BLEConfig)
    sync: SyncConfig = Field(default_factory=SyncConfig)
    api: APIConfig = Field(default_factory=APIConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    # Device configuration
    device_ids: list[str] = Field(default_factory=list)

    class Config:
        """Pydantic configuration."""

        env_prefix = "ECG_"
        env_nested_delimiter = "__"


def load_settings(config_file: Path | None = None) -> Settings:
    """Load settings from file and environment variables.

    Args:
        config_file: Optional path to YAML configuration file

    Returns:
        Loaded settings instance
    """
    settings_dict: dict[str, object] = {}

    # If no config file specified, look for config.yaml in current directory
    if config_file is None:
        default_config = Path("config.yaml")
        if default_config.exists():
            config_file = default_config

    # Load from YAML file if provided
    if config_file and config_file.exists():
        with open(config_file) as f:
            loaded = yaml.safe_load(f)
            settings_dict = loaded if loaded is not None else {}

    # Create settings (environment variables override file settings)
    settings = Settings(**settings_dict)

    return settings


def create_default_config(output_path: Path) -> None:
    """Create a default configuration file.

    Args:
        output_path: Path where to save the default config
    """
    default_settings = Settings()

    config_dict = {
        "ble": default_settings.ble.model_dump(),
        "sync": default_settings.sync.model_dump(),
        "api": default_settings.api.model_dump(),
        "logging": {
            k: str(v) if isinstance(v, Path) else v
            for k, v in default_settings.logging.model_dump().items()
            if v is not None
        },
        "device_ids": [],
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        yaml.dump(config_dict, f, default_flow_style=False, sort_keys=False)
