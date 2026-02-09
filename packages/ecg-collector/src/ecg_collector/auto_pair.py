"""Auto-pairing orchestrator for ESP32 and Polar H10 devices.

This module provides functionality to automatically pair ESP32 devices with
Polar H10 heart rate monitors by discovering both via USB/BLE and creating
optimal device mappings.
"""

from dataclasses import dataclass

from ecg_common.logging import get_logger

from ecg_collector.ble_scanner import scan_polar_devices
from ecg_collector.usb.collector import discover_and_group_usb_interfaces, probe_usb_device

logger = get_logger(__name__)


@dataclass
class EspDeviceState:
    """State of an ESP32 device."""

    esp_id: str
    device_path: str
    current_targets: list[str]
    polar_connected: bool
    config_required: bool


@dataclass
class PairingResult:
    """Result of auto-pairing operation."""

    esp_id: str
    polar_id: str
    device_path: str
    reason: str  # e.g., "new", "reconnect", "already_connected"


async def discover_esp_states(timeout: float = 12.0) -> list[EspDeviceState]:
    """Discover all ESP32 devices and their current states.

    Args:
        timeout: Probe timeout per device in seconds

    Returns:
        List of ESP device states
    """
    logger.info("Discovering ESP devices...")

    # Discover USB devices
    device_groups = await discover_and_group_usb_interfaces()
    if not device_groups:
        logger.warning("No ESP devices found via USB")
        return []

    logger.info(f"Found {len(device_groups)} ESP device(s)")

    # Probe each device to get current state
    esp_states = []
    for group in device_groups.values():
        if not group.data_interface:
            continue

        device_path = group.data_interface.device_path
        try:
            device_info, partial_info = await probe_usb_device(device_path, timeout_s=timeout)
            if device_info:
                esp_states.append(
                    EspDeviceState(
                        esp_id=device_info.esp_id,
                        device_path=device_path,
                        current_targets=device_info.current_targets,
                        polar_connected=device_info.polar_connected,
                        config_required=device_info.config_required,
                    )
                )
                logger.info(
                    f"  ESP {device_info.esp_id}: targets="
                    f"{', '.join(device_info.current_targets) if device_info.current_targets else '<unassigned>'}, "
                    f"polar={'connected' if device_info.polar_connected else 'disconnected'}"
                )
            else:
                # Probe timed out but device exists - add with unknown state
                # Use device path as fallback ID
                fallback_id = f"<probe timeout: {device_path}>"
                if partial_info:
                    logger.warning(
                        f"  ESP at {device_path}: probe timeout, received {partial_info.last_message_type} but no device_info"
                    )
                else:
                    logger.warning(
                        f"  ESP at {device_path}: probe timeout, no device_info received"
                    )
                esp_states.append(
                    EspDeviceState(
                        esp_id=fallback_id,
                        device_path=device_path,
                        current_targets=[],
                        polar_connected=False,
                        config_required=True,
                    )
                )
        except Exception as e:
            # Probe failed with exception - add with error state
            fallback_id = f"<probe error: {device_path}>"
            esp_states.append(
                EspDeviceState(
                    esp_id=fallback_id,
                    device_path=device_path,
                    current_targets=[],
                    polar_connected=False,
                    config_required=True,
                )
            )
            logger.error(f"Failed to probe {device_path}: {e}")

    return esp_states


async def auto_pair_devices(
    ble_scan_timeout: float = 5.0,
    usb_probe_timeout: float = 12.0,
) -> list[PairingResult]:
    """Automatically pair ESP32 devices with Polar H10 monitors.

    Strategy:
    1. Discover all ESP devices and their current states
    2. Identify ESPs that are already connected to Polars (keep these)
    3. Scan for available (unconnected) Polar devices via BLE
    4. Pair unassigned ESPs with available Polars

    Args:
        ble_scan_timeout: BLE scan duration in seconds
        usb_probe_timeout: USB probe timeout per device in seconds

    Returns:
        List of pairing results
    """
    logger.info("Starting auto-pairing process...")

    # Step 1: Discover ESP states
    esp_states = await discover_esp_states(timeout=usb_probe_timeout)
    if not esp_states:
        logger.warning("No ESP devices found - nothing to pair")
        return []

    # Step 2: Identify already-connected pairings
    connected_pairings = []
    unassigned_esps = []

    for esp in esp_states:
        if esp.current_targets and esp.polar_connected:
            # Already connected - keep this pairing
            if len(esp.current_targets) > 1:
                logger.warning(
                    "ESP %s has multiple targets; keeping first for legacy auto_pair: %s",
                    esp.esp_id,
                    ", ".join(esp.current_targets),
                )
            target = esp.current_targets[0]
            connected_pairings.append(
                PairingResult(
                    esp_id=esp.esp_id,
                    polar_id=target,
                    device_path=esp.device_path,
                    reason="already_connected",
                )
            )
            logger.info(f"Keeping existing pairing: ESP {esp.esp_id} -> Polar {target}")
        else:
            # Unassigned or disconnected
            unassigned_esps.append(esp)
            logger.info(f"ESP {esp.esp_id} needs pairing")

    # Step 3: Scan for available Polar devices
    logger.info("Scanning for available Polar devices...")
    polar_devices = await scan_polar_devices(timeout=ble_scan_timeout)

    # Filter out Polars that are already paired
    connected_polar_ids = {p.polar_id for p in connected_pairings}
    available_polars = [p for p in polar_devices if p.device_id not in connected_polar_ids]

    logger.info(
        f"Found {len(polar_devices)} Polar devices ({len(available_polars)} available for pairing)"
    )

    # Step 4: Create new pairings
    new_pairings = []
    for esp, polar in zip(unassigned_esps, available_polars, strict=False):
        new_pairings.append(
            PairingResult(
                esp_id=esp.esp_id,
                polar_id=polar.device_id,
                device_path=esp.device_path,
                reason="new",
            )
        )
        logger.info(f"New pairing: ESP {esp.esp_id} -> Polar {polar.device_id}")

    # Warn about unpaired devices
    if len(unassigned_esps) > len(available_polars):
        unpaired_count = len(unassigned_esps) - len(available_polars)
        logger.warning(
            f"{unpaired_count} ESP(s) could not be paired (not enough available Polar devices)"
        )

    all_pairings = connected_pairings + new_pairings
    logger.info(f"Auto-pairing complete: {len(all_pairings)} total pairings")

    return all_pairings
