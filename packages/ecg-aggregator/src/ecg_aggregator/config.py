"""Configuration management for ECG Aggregator."""

from pathlib import Path
from typing import cast

from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_settings.sources.base import PydanticBaseSettingsSource
from pydantic_settings.sources.providers.yaml import YamlConfigSettingsSource


class GRPCConfig(BaseModel):
    """gRPC server configuration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    port: int = Field(
        default=50051,
        description="gRPC server port for receiving data from collectors",
    )


class SyncConfig(BaseModel):
    """Time synchronization configuration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

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


class APIConfig(BaseModel):
    """API server configuration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

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


class StorageConfig(BaseModel):
    """Database storage configuration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    database_path: Path = Field(
        default=Path("ecg_data.db"),
        description="Path to SQLite database file",
    )
    batch_size: int = Field(
        default=100,
        description="Number of samples per database batch",
    )


class BufferConfig(BaseModel):
    """Data buffer configuration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    duration_seconds: int = Field(
        default=30,
        description="Duration of data to keep in buffer (seconds)",
    )
    max_samples: int = Field(
        default=100000,
        description="Maximum number of samples in buffer",
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


class AggregatorSettings(BaseSettings):
    """Main aggregator configuration."""

    model_config = SettingsConfigDict(
        env_prefix="ECG_AGGREGATOR_",
        env_nested_delimiter="__",
        extra="forbid",
        frozen=True,
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

        settings_type = type(
            f"{cls.__name__}WithYaml",
            (cls,),
            {"model_config": cls.model_config | {"yaml_file": config_path}},
        )
        return cast("AggregatorSettings", settings_type())
