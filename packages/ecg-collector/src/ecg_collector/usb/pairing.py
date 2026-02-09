"""ESP-to-Polar Pairing Logic - Automated N-to-N device matching and configuration."""

import asyncio
import contextlib
from collections.abc import Awaitable, Callable

from ecg_common.logging import get_logger

from ecg_collector.config import DeviceConfig
from ecg_collector.usb.inventory import EspInventoryEntry

logger = get_logger(__name__)


class PairingManager:
    """Manages ESP-to-Polar pairing and configuration."""

    def __init__(
        self,
        devices: dict[str, DeviceConfig],
        default_ecg_sample_rate: int,
        default_acc_sample_rate: int,
        esp_to_device_map: dict[str, str],
        max_targets_per_esp: int,
    ) -> None:
        """Initialize pairing manager.

        Args:
            devices: Device configuration dict (device_id -> DeviceConfig)
            default_ecg_sample_rate: Default ECG sample rate
            default_acc_sample_rate: Default ACC sample rate
            esp_to_device_map: Manual ESP→device mapping from config
        """
        self.devices = devices
        self.default_ecg_sample_rate = default_ecg_sample_rate
        self.default_acc_sample_rate = default_acc_sample_rate
        self.esp_to_device_map = esp_to_device_map
        self.max_targets_per_esp = max_targets_per_esp
        self._last_usb_config: dict[str, tuple[tuple[str, int, int], ...]] = {}
        self._running = False
        self._pairing_task: asyncio.Task | None = None

    def get_last_config(self, esp_id: str) -> tuple[tuple[str, int, int], ...] | None:
        """Get last sent config for an ESP.

        Args:
            esp_id: ESP device ID

        Returns:
            Tuple of (target_device_id, ecg_rate, acc_rate) entries or None
        """
        return self._last_usb_config.get(esp_id)

    def record_config(self, esp_id: str, targets: list[tuple[str, int, int]]) -> None:
        """Record a config that was sent to an ESP.

        Args:
            esp_id: ESP device ID
            targets: List of (target_device_id, ecg_rate, acc_rate)
        """
        self._last_usb_config[esp_id] = tuple(targets)

    def compute_pairings(
        self,
        esp_inventory: dict[str, EspInventoryEntry],
        available_polars: dict[str, object],
    ) -> dict[str, list[str]]:
        """Compute ESP→Polar pairings (manual mappings, preserve, then lexicographic fill).

        Args:
            esp_inventory: ESP inventory dict
            available_polars: Available Polar devices dict

        Returns:
            Dict mapping esp_id to list of polar_ids
        """
        pairings: dict[str, list[str]] = {}

        # Get available ESPs and Polars
        available_esps = list(esp_inventory.keys())
        available_polar_ids = list(available_polars.keys())

        # Step 1: Apply manual ESP→device mappings from config (highest priority)
        used_polars: set[str] = set()
        for esp_id in available_esps:
            manual_target = self.esp_to_device_map.get(esp_id)
            if (
                manual_target
                and manual_target in available_polar_ids
                and manual_target not in used_polars
            ):
                pairings[esp_id] = [manual_target]
                used_polars.add(manual_target)
                logger.debug(f"Manual mapping: ESP {esp_id} → {manual_target}")

        # Step 2: Preserve previously known targets if ESP is online and Polar is available
        for esp_id in available_esps:
            if esp_id not in pairings:
                pairings[esp_id] = []

            preserved_targets: list[str] = []
            last_cfg = self._last_usb_config.get(esp_id)
            if last_cfg:
                preserved_targets.extend([t[0] for t in last_cfg])
            else:
                entry = esp_inventory[esp_id]
                preserved_targets.extend(entry.current_targets)

            for target in preserved_targets:
                if (
                    target in available_polar_ids
                    and target not in used_polars
                    and len(pairings[esp_id]) < self.max_targets_per_esp
                ):
                    pairings[esp_id].append(target)
                    used_polars.add(target)
                    logger.debug(f"Preserved pairing: ESP {esp_id} → {target}")

        # Step 3: Assign remaining ESP slots to remaining Polars (lexicographic)
        unassigned_esps = sorted(available_esps)
        unassigned_polars = sorted([p for p in available_polar_ids if p not in used_polars])

        for esp_id in unassigned_esps:
            if esp_id not in pairings:
                pairings[esp_id] = []
            while unassigned_polars and len(pairings[esp_id]) < self.max_targets_per_esp:
                polar_id = unassigned_polars.pop(0)
                pairings[esp_id].append(polar_id)
                logger.debug(f"Auto-paired: ESP {esp_id} → {polar_id}")

        return pairings

    async def _pairing_loop(
        self,
        get_inventory: Callable[[], dict[str, EspInventoryEntry]],
        get_polars: Callable[[], dict[str, object]],
        send_config: Callable[[str, str, list[tuple[str, int, int]]], Awaitable[None]],
    ) -> None:
        """Match ESPs with Polars and apply configs.

        Args:
            get_inventory: Function to get current ESP inventory
            get_polars: Function to get current available Polars
            send_config: Async function to send config (esp_id, device_path, target, ecg, acc)
        """
        pairing_interval = 10.0  # seconds

        while self._running:
            try:
                # Wait for initial data
                esp_inventory = get_inventory()
                available_polars = get_polars()

                if not esp_inventory or not available_polars:
                    await asyncio.sleep(5.0)
                    continue

                # Compute desired pairings
                pairings = self.compute_pairings(esp_inventory, available_polars)

                # Apply configs where needed
                for esp_id, desired_targets in pairings.items():
                    entry = esp_inventory[esp_id]
                    target_configs: list[tuple[str, int, int]] = []
                    for desired_target in desired_targets:
                        device_config = self.devices.get(desired_target)
                        if device_config:
                            ecg_rate = device_config.ecg_sample_rate or self.default_ecg_sample_rate
                            acc_rate = device_config.acc_sample_rate or self.default_acc_sample_rate
                        else:
                            ecg_rate = self.default_ecg_sample_rate
                            acc_rate = self.default_acc_sample_rate
                        target_configs.append((desired_target, ecg_rate, acc_rate))

                    # Check if config needed
                    needs_config = entry.config_required or self._last_usb_config.get(
                        esp_id
                    ) != tuple(target_configs)

                    if needs_config and target_configs:
                        try:
                            await send_config(esp_id, entry.device_path, target_configs)
                            # Only record config if send succeeded
                            self._last_usb_config[esp_id] = tuple(target_configs)
                            logger.info(
                                "Configured ESP %s → %s",
                                esp_id,
                                ", ".join(
                                    f"{target} (ecg={ecg_rate}, acc={acc_rate})"
                                    for target, ecg_rate, acc_rate in target_configs
                                ),
                            )
                        except Exception as e:
                            # Log error but continue with other ESPs
                            logger.error(f"Failed to configure ESP {esp_id}: {e}")

            except Exception as e:
                logger.error(f"Error in pairing loop: {e}")

            await asyncio.sleep(pairing_interval)

    def start(
        self,
        get_inventory: Callable[[], dict[str, EspInventoryEntry]],
        get_polars: Callable[[], dict[str, object]],
        send_config: Callable[[str, str, list[tuple[str, int, int]]], Awaitable[None]],
    ) -> None:
        """Start pairing loop.

        Args:
            get_inventory: Function to get current ESP inventory
            get_polars: Function to get current available Polars
            send_config: Async function to send config (esp_id, device_path, target, ecg, acc)
        """
        if self._running:
            logger.warning("Pairing manager already running")
            return

        self._running = True
        self._pairing_task = asyncio.create_task(
            self._pairing_loop(get_inventory, get_polars, send_config)
        )
        logger.info("Started pairing loop")

    async def stop(self) -> None:
        """Stop pairing loop."""
        self._running = False

        if self._pairing_task:
            self._pairing_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._pairing_task

        logger.info("Stopped pairing loop")
