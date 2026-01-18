"""Polar H10 BLE device driver implementation."""

import asyncio
import struct
import time

from bleak import BleakClient, BleakScanner
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from ecg_common.logging import get_logger
from ecg_common.models import AccelerometerSample, DeviceStatus, ECGSample

from ecg_collector.ble.drivers.device_driver import DeviceDriver

logger = get_logger(__name__)


# Polar H10 BLE UUIDs
PMD_SERVICE_UUID = "FB005C80-02E7-F387-1CAD-8ACD2D8DF0C8"
PMD_CONTROL_UUID = "FB005C81-02E7-F387-1CAD-8ACD2D8DF0C8"
PMD_DATA_UUID = "FB005C82-02E7-F387-1CAD-8ACD2D8DF0C8"
BATTERY_SERVICE_UUID = "0000180F-0000-1000-8000-00805F9B34FB"
BATTERY_LEVEL_UUID = "00002A19-0000-1000-8000-00805F9B34FB"
DEVICE_INFO_SERVICE_UUID = "0000180A-0000-1000-8000-00805F9B34FB"

# PMD Control Point commands
# START (0x02), ECG type (0x00), setting 0 (sample rate), value 130Hz (0x82), setting 1 (resolution), value 14
ECG_WRITE = bytearray([0x02, 0x00, 0x00, 0x01, 0x82, 0x00, 0x01, 0x01, 0x0E, 0x00])
# START (0x02), ACC type (0x02), setting 0 (sample rate 50Hz = 0x32), setting 1 (resolution 16-bit), setting 2 (range 2G)
# Data is returned as int16 raw ADC values that must be scaled by: range / 32768
ACC_WRITE = bytearray(
    [0x02, 0x02, 0x00, 0x01, 0x32, 0x00, 0x01, 0x01, 0x10, 0x00, 0x02, 0x01, 0x02, 0x00]
)
# STOP (0x03), ECG type (0x00)
ECG_STOP = bytearray([0x03, 0x00])
# STOP (0x03), ACC type (0x02)
ACC_STOP = bytearray([0x03, 0x02])


class PolarH10Driver(DeviceDriver):
    """Polar H10 chest strap driver using Bleak."""

    def __init__(
        self,
        device_id: str,
        address: str | None = None,
        adapter_id: str | None = None,
    ):
        """Initialize Polar H10 driver.

        Args:
            device_id: Unique identifier for this device
            address: BLE MAC address or device name (if known)
            adapter_id: Optional BLE adapter ID (e.g., "hci0")
        """
        super().__init__(device_id, adapter_id)
        self.address = address
        self._client: BleakClient | None = None
        self._ecg_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._acc_queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._disconnection_event = asyncio.Event()

    async def _find_device(self, timeout: float = 10.0) -> BLEDevice | None:
        """Scan for the Polar H10 device.

        Args:
            timeout: Scan timeout in seconds

        Returns:
            BLEDevice if found, None otherwise
        """
        logger.info(f"Scanning for device {self.device_id} (adapter: {self.adapter_id})...")

        def match_device(device: BLEDevice, adv_data: AdvertisementData) -> bool:
            """Check if device matches our target."""
            if self.address:
                # Match by address or name
                return device.address.lower() == self.address.lower() or device.name == self.address
            # Match by device ID in name (e.g., "Polar H10 ABC123")
            return device.name is not None and self.device_id in device.name

        device = await BleakScanner.find_device_by_filter(
            match_device,
            timeout=timeout,
        )

        if device:
            logger.info(f"Found device {self.device_id}: {device.name} ({device.address})")
            self.address = device.address
        else:
            logger.warning(f"Device {self.device_id} not found")

        return device

    async def connect(self) -> bool:
        """Connect to the Polar H10 device."""
        try:
            self._status = DeviceStatus.CONNECTING
            logger.info(f"Connecting to {self.device_id}...")

            # Find device if address not known
            if not self.address:
                device = await self._find_device()
                if not device:
                    self._status = DeviceStatus.ERROR
                    return False

            # Ensure address is set
            if not self.address:
                self._status = DeviceStatus.ERROR
                logger.error(f"No address found for device {self.device_id}")
                return False

            # Create client
            self._client = BleakClient(
                self.address,
                disconnected_callback=self._on_disconnect,
                adapter=self.adapter_id,
            )

            # Connect
            await self._client.connect()

            if self._client.is_connected:
                self._status = DeviceStatus.CONNECTED
                logger.info(f"Connected to {self.device_id}")
                return True
            else:
                self._status = DeviceStatus.ERROR
                logger.error(f"Failed to connect to {self.device_id}")
                return False

        except Exception as e:
            logger.error(f"Error connecting to {self.device_id}: {e}")
            self._status = DeviceStatus.ERROR
            return False

    async def disconnect(self) -> None:
        """Disconnect from the device."""
        try:
            if self._client and self._client.is_connected:
                # Stop streaming first
                await self.stop_streaming()
                await self._client.disconnect()
                logger.info(f"Disconnected from {self.device_id}")

            self._status = DeviceStatus.DISCONNECTED

        except Exception as e:
            logger.error(f"Error disconnecting from {self.device_id}: {e}")
            self._status = DeviceStatus.ERROR

    def _on_disconnect(self, client: BleakClient) -> None:
        """Callback when device disconnects."""
        logger.warning(f"Device {self.device_id} disconnected unexpectedly")
        self._status = DeviceStatus.DISCONNECTED
        self._disconnection_event.set()

    async def start_streaming(self) -> bool:
        """Start streaming ECG data."""
        try:
            if not self._client or not self._client.is_connected:
                logger.error(f"Cannot start streaming: {self.device_id} not connected")
                return False

            # Subscribe to PMD data notifications
            await self._client.start_notify(PMD_DATA_UUID, self._handle_pmd_data)

            # Start ECG measurement
            await self._client.write_gatt_char(PMD_CONTROL_UUID, ECG_WRITE)

            # Wait a bit for ECG to stabilize
            await asyncio.sleep(0.5)

            # Start accelerometer measurement
            await self._client.write_gatt_char(PMD_CONTROL_UUID, ACC_WRITE)

            self._status = DeviceStatus.STREAMING
            logger.info(f"Started ECG and accelerometer streaming on {self.device_id}")
            return True

        except Exception as e:
            logger.error(f"Error starting streaming on {self.device_id}: {e}")
            self._status = DeviceStatus.ERROR
            return False

    async def stop_streaming(self) -> None:
        """Stop streaming ECG and accelerometer data."""
        try:
            if self._client and self._client.is_connected:
                # Stop ECG measurement
                await self._client.write_gatt_char(PMD_CONTROL_UUID, ECG_STOP)

                # Stop accelerometer measurement
                await self._client.write_gatt_char(PMD_CONTROL_UUID, ACC_STOP)

                # Unsubscribe from notifications
                await self._client.stop_notify(PMD_DATA_UUID)

                self._status = DeviceStatus.CONNECTED
                logger.info(f"Stopped ECG and accelerometer streaming on {self.device_id}")

        except Exception as e:
            logger.error(f"Error stopping streaming on {self.device_id}: {e}")

    def _handle_pmd_data(self, sender: BleakGATTCharacteristic, data: bytearray) -> None:
        """Handle incoming PMD data notifications.

        Polar H10 PMD data format:
        - Byte 0: Measurement type (0x00 = ECG, 0x02 = ACC)
        - Byte 1-8: Timestamp (uint64, microseconds)
        - Remaining: Sample data
        """
        try:
            if len(data) < 10:
                return

            measurement_type = data[0]
            device_timestamp_ns = struct.unpack("<Q", data[1:9])[0]  # Nanoseconds
            device_timestamp = device_timestamp_ns / 1000.0  # Convert to microseconds
            host_receive_time = time.time()

            if measurement_type == 0x00:
                # ECG data - skip 10-byte header (including frame type)
                self._parse_ecg_data(data[10:], device_timestamp, host_receive_time)
            elif measurement_type == 0x02:
                # Accelerometer data - skip 10-byte header (including frame type)
                self._parse_acc_data(data[10:], device_timestamp, host_receive_time)
            else:
                logger.warning(
                    f"[{self.device_id}] Unknown measurement type: 0x{measurement_type:02x}"
                )

        except Exception as e:
            logger.error(f"Error parsing PMD data from {self.device_id}: {e}")

    def _parse_ecg_data(
        self, data: bytearray, device_timestamp: float, host_receive_time: float
    ) -> None:
        """Parse ECG sample data.

        ECG samples are 3 bytes each (24-bit signed integers).
        Sample rate is typically 130 Hz for Polar H10.

        Note: device_timestamp represents the timestamp of the LAST sample in the frame.
        """
        try:
            sample_count = len(data) // 3
            sample_rate = 130  # Hz

            for i in range(sample_count):
                # Extract 3-byte signed integer
                sample_bytes = data[i * 3 : (i + 1) * 3]
                raw_value = int.from_bytes(sample_bytes, byteorder="little", signed=True)

                # Calculate timestamp for this sample
                # Timestamp is for the last sample, so work backwards
                sample_offset_us = ((i - sample_count + 1) / sample_rate) * 1_000_000
                sample_timestamp = device_timestamp + sample_offset_us

                sample = ECGSample(
                    device_id=self.device_id,
                    device_timestamp=sample_timestamp,
                    host_receive_time=host_receive_time,
                    raw_value=raw_value,
                    sample_rate=sample_rate,
                )

                # Add to queue (non-blocking)
                try:
                    self._ecg_queue.put_nowait(sample)
                except asyncio.QueueFull:
                    logger.warning(f"ECG queue full for {self.device_id}, dropping sample")

        except Exception as e:
            logger.error(f"Error parsing ECG data from {self.device_id}: {e}")

    def _parse_acc_data(
        self, data: bytearray, device_timestamp: float, host_receive_time: float
    ) -> None:
        """Parse accelerometer sample data.

        ACC samples are 6 bytes each (3x int16 for x, y, z).
        Sample rate is 50 Hz for this implementation.
        Values are in milligravity (mG) units.

        Note: device_timestamp represents the timestamp of the LAST sample in the frame.
        """
        try:
            sample_count = len(data) // 6
            sample_rate = 50  # Hz (configured in ACC_WRITE command)

            for i in range(sample_count):
                # Extract 3x int16 values
                offset = i * 6
                x, y, z = struct.unpack("<hhh", data[offset : offset + 6])

                # Calculate timestamp for this sample
                # Timestamp is for the last sample, so work backwards
                sample_offset_us = ((i - sample_count + 1) / sample_rate) * 1_000_000
                sample_timestamp = device_timestamp + sample_offset_us

                # Polar H10 sends accelerometer data in milligravity (mG) units
                # Convert to g (gravity units) by dividing by 1000
                sample = AccelerometerSample(
                    device_id=self.device_id,
                    device_timestamp=sample_timestamp,
                    host_receive_time=host_receive_time,
                    x=x / 1000.0,
                    y=y / 1000.0,
                    z=z / 1000.0,
                )

                try:
                    self._acc_queue.put_nowait(sample)
                except asyncio.QueueFull:
                    logger.warning(f"ACC queue full for {self.device_id}, dropping sample")

        except Exception as e:
            logger.error(f"Error parsing ACC data from {self.device_id}: {e}")

    async def read_ecg_sample(self) -> ECGSample | None:
        """Read a single ECG sample from the queue."""
        try:
            sample: ECGSample = self._ecg_queue.get_nowait()
            return sample
        except asyncio.QueueEmpty:
            return None

    async def read_accelerometer_sample(self) -> AccelerometerSample | None:
        """Read a single accelerometer sample from the queue."""
        try:
            sample: AccelerometerSample = self._acc_queue.get_nowait()
            return sample
        except asyncio.QueueEmpty:
            return None

    async def get_battery_level(self) -> int | None:
        """Get battery level from device."""
        try:
            if not self._client or not self._client.is_connected:
                return None

            battery_bytes = await self._client.read_gatt_char(BATTERY_LEVEL_UUID)
            battery_level = int(battery_bytes[0])
            return battery_level

        except Exception as e:
            logger.error(f"Error reading battery level from {self.device_id}: {e}")
            return None

    async def get_device_info(self) -> dict[str, object]:
        """Get device information."""
        info: dict[str, object] = {
            "device_id": self.device_id,
            "address": self.address,
            "adapter": self.adapter_id,
            "status": self._status.value,
        }

        try:
            if self._client and self._client.is_connected:
                # Try to read device info characteristics
                info["connected"] = True
                battery = await self.get_battery_level()
                if battery is not None:
                    info["battery_level"] = battery
            else:
                info["connected"] = False

        except Exception as e:
            logger.error(f"Error getting device info for {self.device_id}: {e}")

        return info
