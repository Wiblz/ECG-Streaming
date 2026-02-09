"""USB ESP Inventory Management - Discovery, BLE scanning, and cache updates."""

import asyncio
import contextlib
import time
from dataclasses import dataclass

from ecg_common.logging import get_logger
from ecg_common.proto import esp_collector_pb2

from ecg_collector.usb.collector import (
    discover_and_group_usb_interfaces,
    probe_usb_groups,
)

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
    """Manages ESP device inventory, USB discovery, and BLE scanning."""

    def __init__(self) -> None:
        """Initialize inventory manager."""
        self._esp_inventory: dict[str, EspInventoryEntry] = {}  # esp_id -> entry
        self._device_path_last_seen: dict[
            str, float
        ] = {}  # device_path -> last_seen_ts (for unknown ESPs)
        self._available_polars: set[str] = set()  # device_id set
        self._running = False
        self._discovery_task: asyncio.Task | None = None
        self._ble_scan_task: asyncio.Task | None = None

    @property
    def esp_inventory(self) -> dict[str, EspInventoryEntry]:
        """Get ESP inventory (read-only access)."""
        return self._esp_inventory

    @property
    def available_polars(self) -> set[str]:
        """Get available Polar devices (read-only access)."""
        return self._available_polars

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

            # If no cache entry exists yet, track by device_path only
            # This prevents re-probing devices that are streaming but haven't sent device_info
            if not found:
                self._device_path_last_seen[device_path] = now

    async def _usb_discovery_loop(self) -> None:
        """Periodically discover USB devices and probe new/stale ones."""
        stale_threshold = 30.0  # seconds
        discovery_interval = 15.0  # seconds

        while self._running:
            try:
                logger.info("Running USB discovery scan")
                # Discover all USB devices
                device_groups = await discover_and_group_usb_interfaces()

                # Determine which devices need probing
                now = time.time()
                stale_groups = {}

                for group_key, group in device_groups.items():
                    if not group.data_interface:
                        continue

                    # Check if ESP is in cache and fresh
                    esp_id = None
                    for entry in self._esp_inventory.values():
                        if entry.device_path == group.data_interface.device_path:
                            esp_id = entry.esp_id
                            break

                    # Check staleness: consider both ESP cache AND device_path tracking
                    device_path_last_seen = self._device_path_last_seen.get(
                        group.data_interface.device_path, 0
                    )
                    is_stale = (
                        esp_id is None  # New device not in cache
                        and (now - device_path_last_seen)
                        > stale_threshold  # Not recently tracked by path
                    ) or (
                        esp_id is not None  # Device in cache
                        and (now - self._esp_inventory[esp_id].last_seen_ts)
                        > stale_threshold  # Stale
                    )

                    # Only include stale devices for probing
                    if is_stale:
                        stale_groups[group_key] = group
                    else:
                        # Update cache for fresh devices from existing entry
                        if esp_id:
                            entry = self._esp_inventory[esp_id]
                            # Refresh device_path in case device was re-plugged
                            entry.device_path = group.data_interface.device_path

                # Probe only new/stale devices
                if stale_groups:
                    await probe_usb_groups(stale_groups, timeout_s=12.0, on_update=None)

                    # Update cache from probe results
                    for group in stale_groups.values():
                        if group.device_info and group.data_interface:
                            self._esp_inventory[group.device_info.esp_id] = EspInventoryEntry(
                                esp_id=group.device_info.esp_id,
                                device_path=group.data_interface.device_path,
                                last_seen_ts=now,
                                current_target=group.device_info.current_target,
                                polar_connected=group.device_info.polar_connected,
                                config_required=group.device_info.config_required,
                                app_version=group.device_info.app_version,
                                idf_version=group.device_info.idf_version,
                                protocol_version=group.device_info.protocol_version,
                            )

                logger.info(
                    "USB discovery complete: total=%d probed=%d tracked_esps=%d",
                    len(device_groups),
                    len(stale_groups),
                    len(self._esp_inventory),
                )

            except Exception as e:
                logger.error(f"Error in USB discovery loop: {e}")

            await asyncio.sleep(discovery_interval)

    async def _ble_scan_loop(self) -> None:
        """Periodically scan for available Polar devices."""
        from ecg_collector.ble_scanner import scan_polar_devices

        ble_scan_interval = 45.0  # seconds

        while self._running:
            try:
                logger.info("Running BLE scan for Polar devices")
                polar_devices = await scan_polar_devices(timeout=5.0)
                self._available_polars = {p.device_id for p in polar_devices}
                if self._available_polars:
                    logger.info(
                        "BLE scan found %d Polar devices: %s",
                        len(self._available_polars),
                        ", ".join(sorted(self._available_polars)),
                    )
                else:
                    logger.info("BLE scan found 0 Polar devices")
            except Exception as e:
                logger.error(f"Error in BLE scan loop: {e}")

            await asyncio.sleep(ble_scan_interval)

    def start(self) -> None:
        """Start inventory background loops."""
        if self._running:
            logger.warning("Inventory manager already running")
            return

        self._running = True
        self._discovery_task = asyncio.create_task(self._usb_discovery_loop())
        self._ble_scan_task = asyncio.create_task(self._ble_scan_loop())
        logger.info("Started inventory management loops")

    async def stop(self) -> None:
        """Stop inventory background loops."""
        self._running = False

        tasks = [self._discovery_task, self._ble_scan_task]
        for task in tasks:
            if task:
                task.cancel()

        for task in tasks:
            if task:
                with contextlib.suppress(asyncio.CancelledError):
                    await task

        logger.info("Stopped inventory management loops")
