"""Shared BLE scanning functionality for Polar devices.

This module provides reusable BLE scanning functions that can be used by both
BLE and USB collectors to discover and identify Polar H10 devices.
"""

from dataclasses import dataclass

from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from ecg_common.logging import get_logger

logger = get_logger(__name__)


@dataclass
class PolarDeviceInfo:
    """Information about a discovered Polar device."""

    device_id: str  # Full device name (e.g., "Polar H10 A1B2C3D4")
    short_id: str  # Short device ID suffix (e.g., "A1B2C3D4")
    name: str  # Full device name (e.g., "Polar H10 A1B2C3D4")
    address: str  # BLE MAC address
    rssi: int | None  # Signal strength


async def scan_polar_devices(timeout: float = 5.0) -> list[PolarDeviceInfo]:
    """Scan for all Polar BLE devices.

    Args:
        timeout: Scan duration in seconds

    Returns:
        List of discovered Polar devices
    """
    logger.info(f"Scanning for Polar devices (timeout={timeout}s)...")

    devices = await BleakScanner.discover(timeout=timeout)

    polar_devices = []
    for device in devices:
        if device.name and "Polar" in device.name:
            # Extract short ID from name (e.g., "Polar H10 A1B2C3D4" -> "A1B2C3D4")
            short_id = device.name.split()[-1] if len(device.name.split()) > 1 else device.name

            # Get RSSI if available
            rssi = None
            if hasattr(device, "details") and hasattr(device.details, "rssi"):
                rssi = device.details.rssi

            polar_devices.append(
                PolarDeviceInfo(
                    device_id=device.name,
                    short_id=short_id,
                    name=device.name,
                    address=device.address,
                    rssi=rssi,
                )
            )

    logger.info(f"Found {len(polar_devices)} Polar devices")
    for polar_device in polar_devices:
        logger.debug(f"  {polar_device.name} ({polar_device.address}) RSSI: {polar_device.rssi}")

    return polar_devices


async def find_polar_device(
    device_id: str,
    address: str | None = None,
    timeout: float = 10.0,
) -> BLEDevice | None:
    """Find a specific Polar device by ID or address.

    Args:
        device_id: Polar device ID to find (e.g., "A1B2C3D4")
        address: Optional BLE MAC address to match
        timeout: Scan timeout in seconds

    Returns:
        BLEDevice if found, None otherwise
    """
    logger.info(f"Searching for Polar device {device_id}...")

    def match_device(device: BLEDevice, adv_data: AdvertisementData) -> bool:
        """Check if device matches our target."""
        if address:
            # Match by address or name
            return device.address.lower() == address.lower() or device.name == address

        # Match by device ID in name (e.g., "Polar H10 ABC123")
        return device.name is not None and device_id in device.name

    device = await BleakScanner.find_device_by_filter(
        match_device,
        timeout=timeout,
    )

    if device:
        logger.info(f"Found device {device_id}: {device.name} ({device.address})")
    else:
        logger.warning(f"Device {device_id} not found")

    return device
