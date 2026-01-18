"""USB Collector for ESP32-based devices.

Reads protobuf messages from USB serial port using length-prefixed UsbFrame protocol.
"""

import asyncio
import struct
import time
from collections.abc import Callable, Coroutine
from pathlib import Path

import serial
from ecg_common.logging import get_logger
from ecg_common.proto import ecg_streaming_pb2

logger = get_logger(__name__)


class UsbCollector:
    """Collects data from ESP32 device via USB serial port."""

    def __init__(
        self,
        device_path: str,
        baudrate: int = 115200,
        message_callback: Callable[
            [ecg_streaming_pb2.CollectorMessage], Coroutine[None, None, None]
        ]
        | None = None,
    ) -> None:
        """Initialize USB collector.

        Args:
            device_path: Path to USB serial device (e.g., /dev/ttyACM0)
            baudrate: Serial baud rate (default 115200)
            message_callback: Async callback function for received CollectorMessages
        """
        self.device_path = device_path
        self.baudrate = baudrate
        self.message_callback = message_callback
        self.serial_port: serial.Serial | None = None
        self.running = False
        self.stats = {
            "frames_received": 0,
            "frames_crc_errors": 0,
            "frames_parse_errors": 0,
            "messages_received": 0,
            "bytes_received": 0,
        }

    async def connect(self) -> None:
        """Open serial port connection."""
        try:
            self.serial_port = serial.Serial(
                port=self.device_path,
                baudrate=self.baudrate,
                timeout=1.0,  # 1 second read timeout
                write_timeout=1.0,
            )
            logger.info(f"Connected to USB device: {self.device_path} @ {self.baudrate} baud")
        except (serial.SerialException, OSError) as e:
            logger.error(f"Failed to open serial port {self.device_path}: {e}")
            raise

    async def disconnect(self) -> None:
        """Close serial port connection."""
        if self.serial_port and self.serial_port.is_open:
            self.serial_port.close()
            logger.info(f"Disconnected from USB device: {self.device_path}")

    def _read_exact(self, n: int) -> bytes | None:
        """Read exactly n bytes from serial port.

        Returns:
            Bytes read, or None if timeout/error
        """
        if not self.serial_port:
            return None

        data = bytearray()
        deadline = time.monotonic() + 5.0  # 5 second total timeout

        while len(data) < n:
            if time.monotonic() > deadline:
                logger.warning(f"Timeout reading {n} bytes (got {len(data)})")
                return None

            try:
                remaining = n - len(data)
                chunk = self.serial_port.read(remaining)
                if not chunk:
                    # No data available, yield to event loop
                    continue
                data.extend(chunk)
            except (serial.SerialException, OSError) as e:
                logger.error(f"Serial read error: {e}")
                return None

        return bytes(data)

    def _crc32_ieee(self, data: bytes) -> int:
        """Calculate CRC-32/IEEE checksum.

        Args:
            data: Bytes to checksum

        Returns:
            CRC-32 value
        """
        crc = 0xFFFFFFFF
        for byte in data:
            crc ^= byte
            for _ in range(8):
                mask = -(crc & 1)
                crc = (crc >> 1) ^ (0xEDB88320 & mask)
        return crc ^ 0xFFFFFFFF

    async def _process_frame(self, frame_bytes: bytes) -> None:
        """Parse and process a UsbFrame.

        Args:
            frame_bytes: Serialized UsbFrame protobuf
        """
        try:
            # Parse UsbFrame
            usb_frame = ecg_streaming_pb2.UsbFrame()
            usb_frame.ParseFromString(frame_bytes)

            # Verify CRC
            computed_crc = self._crc32_ieee(usb_frame.payload)
            if computed_crc != usb_frame.crc32:
                self.stats["frames_crc_errors"] += 1
                logger.warning(
                    f"CRC mismatch: expected {usb_frame.crc32:08x}, got {computed_crc:08x}"
                )
                return

            self.stats["frames_received"] += 1

            # Parse payload based on type
            if usb_frame.payload_type == ecg_streaming_pb2.USB_PAYLOAD_TYPE_COLLECTOR_MESSAGE:
                collector_msg = ecg_streaming_pb2.CollectorMessage()
                collector_msg.ParseFromString(usb_frame.payload)
                self.stats["messages_received"] += 1

                # Invoke callback
                if self.message_callback:
                    await self.message_callback(collector_msg)

            else:
                logger.warning(f"Unknown payload type: {usb_frame.payload_type}")

        except Exception as e:
            self.stats["frames_parse_errors"] += 1
            logger.error(f"Failed to parse frame: {e}")

    async def run(self) -> None:
        """Main loop to read and process frames."""
        self.running = True
        logger.info(f"Starting USB collector for {self.device_path}")

        try:
            await self.connect()

            while self.running:
                if not self.serial_port or not self.serial_port.is_open:
                    logger.error("Serial port not open")
                    break

                # Read frame length (4 bytes, little-endian)
                length_bytes = self._read_exact(4)
                if not length_bytes:
                    # Timeout or error, retry
                    await asyncio.sleep(0.1)
                    continue

                frame_length = struct.unpack("<I", length_bytes)[0]

                # Sanity check frame length
                if frame_length == 0 or frame_length > 1024 * 1024:  # 1MB max
                    logger.error(f"Invalid frame length: {frame_length}")
                    # Try to resync by reading byte-by-byte until we find a valid length
                    continue

                # Read frame data
                frame_bytes = self._read_exact(frame_length)
                if not frame_bytes:
                    logger.warning(f"Failed to read frame of {frame_length} bytes")
                    continue

                self.stats["bytes_received"] += len(frame_bytes) + 4

                # Process frame
                await self._process_frame(frame_bytes)

        except KeyboardInterrupt:
            logger.info("USB collector interrupted")
        except Exception as e:
            logger.error(f"USB collector error: {e}", exc_info=True)
        finally:
            self.running = False
            await self.disconnect()

    async def stop(self) -> None:
        """Stop the collector."""
        self.running = False

    def get_stats(self) -> dict:
        """Get collector statistics.

        Returns:
            Dictionary with statistics
        """
        return self.stats.copy()


async def discover_usb_devices() -> list[str]:
    """Discover available USB serial devices.

    Returns:
        List of device paths (e.g., ['/dev/ttyACM0', '/dev/ttyUSB0'])
    """
    devices: list[str] = []

    # Linux: check /dev/ttyACM* and /dev/ttyUSB*
    dev_path = Path("/dev")
    if dev_path.exists():
        for pattern in ["ttyACM*", "ttyUSB*"]:
            devices.extend(str(p) for p in dev_path.glob(pattern))

    # macOS: check /dev/cu.usbmodem* and /dev/cu.usbserial*
    for pattern in ["cu.usbmodem*", "cu.usbserial*"]:
        devices.extend(str(p) for p in dev_path.glob(pattern))

    return sorted(devices)
