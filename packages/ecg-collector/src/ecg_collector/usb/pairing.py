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
        self._last_usb_config: dict[str, tuple[str, int, int]] = {}  # esp_id -> (target, ecg, acc)
        self._running = False
        self._pairing_task: asyncio.Task | None = None

    def get_last_config(self, esp_id: str) -> tuple[str, int, int] | None:
        """Get last sent config for an ESP.

        Args:
            esp_id: ESP device ID

        Returns:
            Tuple of (target_device_id, ecg_rate, acc_rate) or None
        """
        return self._last_usb_config.get(esp_id)

    def record_config(
        self, esp_id: str, target_device_id: str, ecg_rate: int, acc_rate: int
    ) -> None:
        """Record a config that was sent to an ESP.

        Args:
            esp_id: ESP device ID
            target_device_id: Target Polar device ID
            ecg_rate: ECG sample rate
            acc_rate: ACC sample rate
        """
        self._last_usb_config[esp_id] = (target_device_id, ecg_rate, acc_rate)

    def compute_pairings(
        self,
        esp_inventory: dict[str, EspInventoryEntry],
        available_polars: dict[str, object],
    ) -> dict[str, str]:
        """Compute ESP→Polar pairings (manual mappings first, then preserve existing, then lexicographic).

        Args:
            esp_inventory: ESP inventory dict
            available_polars: Available Polar devices dict

        Returns:
            Dict mapping esp_id to polar_id
        """
        pairings: dict[str, str] = {}

        # Get available ESPs and Polars
        available_esps = list(esp_inventory.keys())
        available_polar_ids = list(available_polars.keys())

        # Step 1: Apply manual ESP→device mappings from config (highest priority)
        used_polars = set()
        for esp_id in available_esps:
            manual_target = self.esp_to_device_map.get(esp_id)
            if manual_target and manual_target in available_polar_ids:
                pairings[esp_id] = manual_target
                used_polars.add(manual_target)
                logger.debug(f"Manual mapping: ESP {esp_id} → {manual_target}")

        # Step 2: Preserve current_target if ESP is online and Polar is available (medium priority)
        for esp_id in available_esps:
            if esp_id in pairings:  # Already has manual mapping
                continue
            entry = esp_inventory[esp_id]
            if (
                entry.current_target
                and entry.current_target in available_polar_ids
                and entry.current_target not in used_polars
            ):
                pairings[esp_id] = entry.current_target
                used_polars.add(entry.current_target)
                logger.debug(f"Preserved pairing: ESP {esp_id} → {entry.current_target}")

        # Step 3: Assign remaining ESPs to remaining Polars (lexicographic, lowest priority)
        unassigned_esps = sorted([e for e in available_esps if e not in pairings])
        unassigned_polars = sorted([p for p in available_polar_ids if p not in used_polars])

        for esp_id, polar_id in zip(unassigned_esps, unassigned_polars, strict=False):
            pairings[esp_id] = polar_id
            logger.debug(f"Auto-paired: ESP {esp_id} → {polar_id}")

        return pairings

    async def _pairing_loop(
        self,
        get_inventory: Callable[[], dict[str, EspInventoryEntry]],
        get_polars: Callable[[], dict[str, object]],
        send_config: Callable[[str, str, str, int, int], Awaitable[None]],
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
                for esp_id, desired_target in pairings.items():
                    entry = esp_inventory[esp_id]
                    device_config = self.devices.get(desired_target)

                    # Use device config if available, otherwise use defaults for auto-pairing
                    if device_config:
                        ecg_rate = device_config.ecg_sample_rate or self.default_ecg_sample_rate
                        acc_rate = device_config.acc_sample_rate or self.default_acc_sample_rate
                    else:
                        # Auto-pairing with discovered Polar not in config - use defaults
                        ecg_rate = self.default_ecg_sample_rate
                        acc_rate = self.default_acc_sample_rate

                    # Check if config needed
                    needs_config = (
                        entry.config_required
                        or entry.current_target != desired_target
                        or self._last_usb_config.get(esp_id) != (desired_target, ecg_rate, acc_rate)
                    )

                    if needs_config:
                        try:
                            await send_config(
                                esp_id, entry.device_path, desired_target, ecg_rate, acc_rate
                            )
                            # Only record config if send succeeded
                            self._last_usb_config[esp_id] = (desired_target, ecg_rate, acc_rate)
                            logger.info(
                                f"Configured ESP {esp_id} → {desired_target} "
                                f"(ecg={ecg_rate}, acc={acc_rate})"
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
        send_config: Callable[[str, str, str, int, int], Awaitable[None]],
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
