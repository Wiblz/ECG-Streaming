"""USB ESP Inventory Management - BLE availability and cache updates."""

import time
from dataclasses import dataclass

from ecg_common.logging import get_logger
from ecg_common.proto import esp_collector_pb2

from ecg_collector.ble.discovery import BleDiscoveryManager

logger = get_logger(__name__)


@dataclass
class EspInventoryEntry:
    """ESP device inventory entry with state tracking."""

    esp_id: str
    device_path: str
    last_seen_ts: float  # Updated on ANY message
    current_target: str | None
    polar_connected: bool
    config_required: bool
    app_version: str
    idf_version: str
    protocol_version: int


class EspInventoryManager:
    """Manages ESP device inventory and BLE scanning."""

    def __init__(self) -> None:
        """Initialize inventory manager."""
        self._esp_inventory: dict[str, EspInventoryEntry] = {}  # esp_id -> entry
        self._running = False
        self._ble_discovery = BleDiscoveryManager()

    @property
    def esp_inventory(self) -> dict[str, EspInventoryEntry]:
        """Get ESP inventory (read-only access)."""
        return self._esp_inventory

    @property
    def available_polars(self) -> set[str]:
        """Get available Polar devices (read-only access)."""
        return self._ble_discovery.available_polars

    def update_cache_from_message(
        self, esp_msg: esp_collector_pb2.EspMessage, device_path: str
    ) -> None:
        """Update ESP inventory cache from any incoming message.

        Args:
            esp_msg: ESP message (device_info or sensor_frame)
            device_path: USB device path
        """
        msg_type = esp_msg.WhichOneof("message")

        if msg_type == "device_info":
            info = esp_msg.device_info
            self._esp_inventory[info.esp_id] = EspInventoryEntry(
                esp_id=info.esp_id,
                device_path=device_path,
                last_seen_ts=time.time(),
                current_target=info.current_target,
                polar_connected=info.polar_connected,
                config_required=info.config_required,
                app_version=info.app_version,
                idf_version=info.idf_version,
                protocol_version=info.protocol_version,
            )
        elif msg_type in ["sensor_frame"]:
            # Update timestamp for active streaming ESPs
            now = time.time()

            # Try to find ESP in inventory by device_path
            found = False
            for entry in self._esp_inventory.values():
                if entry.device_path == device_path:
                    entry.last_seen_ts = now
                    found = True
                    break
            if not found:
                return

    def drop_device_path(self, device_path: str) -> None:
        """Remove inventory entries associated with a USB device path."""
        to_remove = [
            esp_id
            for esp_id, entry in self._esp_inventory.items()
            if entry.device_path == device_path
        ]
        for esp_id in to_remove:
            del self._esp_inventory[esp_id]
        if to_remove:
            logger.info("Dropped %d ESP inventory entries for %s", len(to_remove), device_path)

    def prune_stale(self, max_age_s: float) -> None:
        """Remove ESP inventory entries that have not been seen recently."""
        now = time.time()
        stale_ids = [
            esp_id
            for esp_id, entry in self._esp_inventory.items()
            if (now - entry.last_seen_ts) > max_age_s
        ]
        for esp_id in stale_ids:
            del self._esp_inventory[esp_id]
        if stale_ids:
            logger.info("Pruned %d stale ESP inventory entries", len(stale_ids))

    def start(self) -> None:
        """Start inventory background loops."""
        if self._running:
            logger.warning("Inventory manager already running")
            return

        self._running = True
        self._ble_discovery.start()
        logger.info("Started inventory management loops")

    async def stop(self) -> None:
        """Stop inventory background loops."""
        self._running = False

        await self._ble_discovery.stop()
        logger.info("Stopped inventory management loops")
