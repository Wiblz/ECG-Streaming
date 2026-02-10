"""Shared BLE discovery manager for Polar devices."""

import asyncio
import contextlib

from ecg_common.logging import get_logger

from ecg_collector.ble_scanner import PolarDeviceInfo, scan_polar_devices

logger = get_logger(__name__)


class BleDiscoveryManager:
    """Periodically scans for Polar devices and caches availability."""

    def __init__(self, scan_interval_s: float = 45.0, scan_timeout_s: float = 5.0) -> None:
        self._scan_interval_s = scan_interval_s
        self._scan_timeout_s = scan_timeout_s
        self._available: dict[str, PolarDeviceInfo] = {}
        self._running = False
        self._scan_task: asyncio.Task | None = None

    @property
    def available_polars(self) -> set[str]:
        """Get available Polar device IDs (read-only)."""
        return set(self._available.keys())

    def get_address(self, device_id: str) -> str | None:
        """Return the last known BLE address for a device ID, if available."""
        info = self._available.get(device_id)
        return info.address if info else None

    def get_devices(self) -> dict[str, PolarDeviceInfo]:
        """Return a snapshot of the current discovered devices."""
        return dict(self._available)

    async def scan_once(self) -> None:
        """Run a single scan and update cache."""
        devices = await scan_polar_devices(timeout=self._scan_timeout_s)
        self._available = {device.device_id: device for device in devices}

    async def _scan_loop(self) -> None:
        while self._running:
            try:
                await self.scan_once()
                if self._available:
                    logger.info(
                        "BLE scan found %d Polar devices: %s",
                        len(self._available),
                        ", ".join(sorted(self._available.keys())),
                    )
                else:
                    logger.info("BLE scan found 0 Polar devices")
            except Exception as e:
                logger.error("Error in BLE scan loop: %s", e)

            await asyncio.sleep(self._scan_interval_s)

    def start(self) -> None:
        """Start background scanning loop."""
        if self._running:
            logger.warning("BLE discovery manager already running")
            return
        self._running = True
        self._scan_task = asyncio.create_task(self._scan_loop())
        logger.info("Started BLE discovery manager")

    async def stop(self) -> None:
        """Stop background scanning loop."""
        self._running = False
        if self._scan_task:
            self._scan_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._scan_task
        self._scan_task = None
        logger.info("Stopped BLE discovery manager")
