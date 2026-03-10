"""USB ESP Inventory Management - BLE availability and cache updates."""

import time
from dataclasses import dataclass
from typing import cast

from ecg_common.logging import get_logger
from ecg_common.proto import esp_collector_pb2

from ecg_collector.ble.discovery import BleDiscoveryManager

logger = get_logger(__name__)

type EspOperationalMessage = esp_collector_pb2.EspMessage
type EspDiscoveryMessage = esp_collector_pb2.EspDiscoveryMessage
type UsbInboundMessage = EspOperationalMessage | EspDiscoveryMessage


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
    scanner_active: bool
    scanner_request_id: int


class EspInventoryManager:
    """Manages ESP device inventory and BLE scanning."""

    def __init__(self, scan_result_ttl_s: float = 30.0) -> None:
        """Initialize inventory manager."""
        self._esp_inventory: dict[str, EspInventoryEntry] = {}  # esp_id -> entry
        self._running = False
        self._ble_discovery = BleDiscoveryManager()
        self._scan_result_ttl_s = scan_result_ttl_s
        self._esp_scan_sightings: dict[
            str, float
        ] = {}  # polar device id -> last seen wall clock seconds

    @property
    def esp_inventory(self) -> dict[str, EspInventoryEntry]:
        """Get ESP inventory (read-only access)."""
        return self._esp_inventory

    @property
    def available_polars(self) -> set[str]:
        """Get available Polar devices (read-only access)."""
        now = time.time()
        stale_ids = [
            device_id
            for device_id, last_seen_ts in self._esp_scan_sightings.items()
            if (now - last_seen_ts) > self._scan_result_ttl_s
        ]
        for device_id in stale_ids:
            del self._esp_scan_sightings[device_id]

        host_discovered = self._ble_discovery.available_polars
        esp_discovered = set(self._esp_scan_sightings.keys())
        return host_discovered | esp_discovered

    @property
    def scanner_esp_ids(self) -> set[str]:
        """Get ESPs currently flagged as scanner active."""
        return {esp_id for esp_id, entry in self._esp_inventory.items() if entry.scanner_active}

    @property
    def host_ble_available(self) -> bool | None:
        """Return whether host BLE scanning capability is available."""
        return self._ble_discovery.host_ble_available

    def update_cache_from_message(self, esp_msg: UsbInboundMessage, device_path: str) -> None:
        """Update ESP inventory cache from any incoming message.

        Args:
            esp_msg: ESP message (device_info or sensor_frame)
            device_path: USB device path
        """
        msg_type = esp_msg.WhichOneof("message")

        if msg_type == "device_info":
            info = cast(EspOperationalMessage, esp_msg).device_info
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
                scanner_active=info.scanner_active,
                scanner_request_id=info.scanner_request_id,
            )
        elif msg_type == "ble_scan_result":
            now = time.time()
            discovery_msg = cast(EspDiscoveryMessage, esp_msg)
            esp_id = discovery_msg.ble_scan_result.esp_id
            if esp_id in self._esp_inventory:
                self._esp_inventory[esp_id].last_seen_ts = now
            for sighting in discovery_msg.ble_scan_result.sightings:
                if sighting.device_id:
                    self._esp_scan_sightings[sighting.device_id] = now
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
