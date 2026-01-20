"""USB Collector for ESP32-based devices.

Reads protobuf messages from USB serial port using length-prefixed UsbFrame protocol.
"""

import asyncio
import contextlib
import struct
import time
import zlib
from collections.abc import Callable, Coroutine
from pathlib import Path

import serial
import serial_asyncio
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
        stats_interval_s: float = 5.0,
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
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None
        self.running = False
        self.stats_interval_s = stats_interval_s
        self._last_stats_log = time.monotonic()
        self.stats = {
            "frames_received": 0,
            "frames_crc_errors": 0,
            "frames_parse_errors": 0,
            "messages_received": 0,
            "bytes_received": 0,
        }
        self._tx_seq = 0

    async def connect(self) -> None:
        """Open serial port connection."""
        try:
            self.reader, self.writer = await serial_asyncio.open_serial_connection(
                url=self.device_path,
                baudrate=self.baudrate,
            )
            logger.info(f"Connected to USB device: {self.device_path} @ {self.baudrate} baud")
        except (serial.SerialException, OSError) as e:
            logger.error(f"Failed to open serial port {self.device_path}: {e}")
            raise

    async def disconnect(self) -> None:
        """Close serial port connection."""
        if self.writer:
            self.writer.close()
            with contextlib.suppress(Exception):
                await self.writer.wait_closed()
        self.reader = None
        self.writer = None
        logger.info(f"Disconnected from USB device: {self.device_path}")

    def _crc32_ieee(self, data: bytes) -> int:
        """Calculate CRC-32/IEEE checksum.

        Args:
            data: Bytes to checksum

        Returns:
            CRC-32 value
        """
        return zlib.crc32(data) & 0xFFFFFFFF

    async def send_aggregator_message(self, message: ecg_streaming_pb2.AggregatorMessage) -> None:
        """Send an AggregatorMessage to the USB device."""
        if not self.writer:
            raise RuntimeError("USB writer not initialized")

        payload = message.SerializeToString()
        usb_frame = ecg_streaming_pb2.UsbFrame(
            version=1,
            payload_type=ecg_streaming_pb2.USB_PAYLOAD_TYPE_AGGREGATOR_MESSAGE,
            seq=self._tx_seq,
            crc32=self._crc32_ieee(payload),
            payload=payload,
        )
        self._tx_seq = (self._tx_seq + 1) & 0xFFFFFFFF

        frame_bytes = usb_frame.SerializeToString()
        frame_len = struct.pack("<I", len(frame_bytes))
        self.writer.write(frame_len + frame_bytes)
        await self.writer.drain()

    async def _process_frame(self, frame_bytes: bytes) -> bool:
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
                return False

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

            return True
        except Exception as e:
            self.stats["frames_parse_errors"] += 1
            logger.error(f"Failed to parse frame: {e}")
            return False

    async def run(self) -> None:
        """Main loop to read and process frames."""
        self.running = True
        logger.info(f"Starting USB collector for {self.device_path}")

        try:
            await self.connect()

            buffer = bytearray()
            max_frame_len = 4096

            while self.running:
                if not self.reader or not self.writer:
                    logger.error("Serial connection not open")
                    break

                try:
                    chunk = await self.reader.read(1024)
                except (serial.SerialException, OSError) as e:
                    logger.error(f"Serial read error: {e}")
                    break
                if not chunk:
                    await asyncio.sleep(0.01)
                    continue

                buffer.extend(chunk)
                self.stats["bytes_received"] += len(chunk)

                while len(buffer) >= 4:
                    frame_length = struct.unpack_from("<I", buffer, 0)[0]

                    if frame_length == 0 or frame_length > max_frame_len:
                        buffer.pop(0)
                        continue

                    if len(buffer) < 4 + frame_length:
                        break

                    frame_bytes = bytes(buffer[4 : 4 + frame_length])
                    ok = await self._process_frame(frame_bytes)

                    if ok:
                        del buffer[: 4 + frame_length]
                    else:
                        buffer.pop(0)

                now = time.monotonic()
                if now - self._last_stats_log >= self.stats_interval_s:
                    self._last_stats_log = now
                    logger.info(
                        "USB stats: frames=%d crc_errors=%d parse_errors=%d messages=%d bytes=%d",
                        self.stats["frames_received"],
                        self.stats["frames_crc_errors"],
                        self.stats["frames_parse_errors"],
                        self.stats["messages_received"],
                        self.stats["bytes_received"],
                    )

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
