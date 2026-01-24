"""Logging configuration for ECG Streaming application."""

import json
import logging
import sys
from pathlib import Path
from datetime import datetime, timezone


class JsonLineFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        extra = getattr(record, "ble_debug", None)
        if isinstance(extra, dict):
            payload.update(extra)
        return json.dumps(payload, ensure_ascii=True)


def setup_logging(
    level: str = "INFO",
    log_file: Path | None = None,
    ble_debug_file: Path | None = None,
    log_format: str = "detailed",
) -> None:
    """Configure application-wide logging.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional path to log file
        log_format: Format style - "simple" or "detailed"
    """
    # Define log formats
    formats = {
        "simple": "%(levelname)s: %(message)s",
        "detailed": "%(asctime)s | %(name)-30s | %(levelname)-8s | %(message)s",
    }

    log_format_str = formats.get(log_format, formats["detailed"])
    date_format = "%Y-%m-%d %H:%M:%S"

    # Create formatters
    formatter = logging.Formatter(log_format_str, datefmt=date_format)

    # Setup root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))

    # Remove existing handlers
    root_logger.handlers.clear()

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, level.upper()))
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler (optional)
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)  # Always log everything to file
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    # BLE debug file handler (optional)
    if ble_debug_file:
        ble_debug_file.parent.mkdir(parents=True, exist_ok=True)
        ble_debug_handler = logging.FileHandler(ble_debug_file)
        ble_debug_handler.setLevel(logging.DEBUG)
        ble_debug_handler.setFormatter(JsonLineFormatter())
        ble_logger = logging.getLogger("ecg_collector.ble_debug")
        ble_logger.handlers.clear()
        ble_logger.setLevel(logging.DEBUG)
        ble_logger.addHandler(ble_debug_handler)
        ble_logger.propagate = False

    # Reduce noise from third-party libraries
    logging.getLogger("bleak").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("fastapi").setLevel(logging.INFO)
    logging.getLogger("grpc").setLevel(logging.INFO)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance for a module.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)
