"""Configuration management for ECG Aggregator."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class GRPCConfig(BaseSettings):
    """gRPC server configuration."""

    port: int = Field(
        default=50051,
        description="gRPC server port for receiving data from collectors",
    )


class SyncConfig(BaseSettings):
    """Time synchronization configuration."""

    window_size: int = Field(
        default=100,
        description="Size of sliding window for sync",
    )
    min_samples: int = Field(
        default=5,
        description="Minimum samples needed to calculate offset",
    )
    buffer_confidence_threshold: float = Field(
        default=0.8,
        description="Minimum confidence to add samples to buffer",
    )


class APIConfig(BaseSettings):
    """API server configuration."""

    port: int = Field(
        default=8000,
        description="HTTP/WebSocket API server port",
    )
    websocket_fps: int = Field(
        default=30,
        description="WebSocket broadcast rate in FPS",
    )
    cors_origins: list[str] = Field(
        default_factory=lambda: ["*"],
        description="CORS allowed origins",
    )


class StorageConfig(BaseSettings):
    """Database storage configuration."""

    database_path: Path = Field(
        default=Path("ecg_data.db"),
        description="Path to SQLite database file",
    )
    batch_size: int = Field(
        default=100,
        description="Number of samples per database batch",
    )


class BufferConfig(BaseSettings):
    """Data buffer configuration."""

    duration_seconds: int = Field(
        default=30,
        description="Duration of data to keep in buffer (seconds)",
    )
    max_samples: int = Field(
        default=100000,
        description="Maximum number of samples in buffer",
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


class AggregatorSettings(BaseSettings):
    """Main aggregator configuration."""

    model_config = SettingsConfigDict(
        env_prefix="ECG_AGGREGATOR_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    grpc: GRPCConfig = Field(
        default_factory=GRPCConfig,
        description="gRPC server settings",
    )

    sync: SyncConfig = Field(
        default_factory=SyncConfig,
        description="Time synchronization settings",
    )

    api: APIConfig = Field(
        default_factory=APIConfig,
        description="API server settings",
    )

    storage: StorageConfig = Field(
        default_factory=StorageConfig,
        description="Database storage settings",
    )

    buffer: BufferConfig = Field(
        default_factory=BufferConfig,
        description="Data buffer settings",
    )

    logging: LoggingConfig = Field(
        default_factory=LoggingConfig,
        description="Logging configuration",
    )

    @classmethod
    def from_yaml(cls, config_path: Path) -> AggregatorSettings:
        """Load configuration from a YAML file.

        Args:
            config_path: Path to the YAML configuration file

        Returns:
            AggregatorSettings instance

        Note:
            Environment variables override YAML values.
            Use ECG_AGGREGATOR_* prefix (e.g., ECG_AGGREGATOR_STORAGE__DATABASE_PATH).
        """
        import os

        import yaml

        with open(config_path) as f:
            config_data = yaml.safe_load(f) or {}

        # Check which env vars are actually set
        env_prefix = "ECG_AGGREGATOR_"
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
