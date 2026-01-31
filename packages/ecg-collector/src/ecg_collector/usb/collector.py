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
from ecg_common.proto import esp_collector_pb2, usb_transport_pb2

from .models import EspDeviceGroup, InterfaceType, UsbInterfaceInfo

logger = get_logger(__name__)


class UsbCollector:
    """Collects data from ESP32 device via USB serial port."""

    def __init__(
        self,
        device_path: str,
        baudrate: int = 115200,
        message_callback: Callable[[esp_collector_pb2.EspMessage], Coroutine[None, None, None]]
        | None = None,
        stats_interval_s: float = 5.0,
    ) -> None:
        """Initialize USB collector.

        Args:
            device_path: Path to USB serial device (e.g., /dev/ttyACM0)
            baudrate: Serial baud rate (default 115200)
            message_callback: Async callback function for received EspMessages from ESP32
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

    async def send_collector_to_esp_message(
        self, message: esp_collector_pb2.CollectorToEspMessage
    ) -> None:
        """Send a CollectorToEspMessage to the USB device."""
        if not self.writer:
            raise RuntimeError("USB writer not initialized")

        payload = message.SerializeToString()
        usb_frame = usb_transport_pb2.UsbFrame(
            version=1,
            payload_type=usb_transport_pb2.USB_PAYLOAD_TYPE_COLLECTOR_TO_ESP,
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
            usb_frame = usb_transport_pb2.UsbFrame()
            usb_frame.ParseFromString(frame_bytes)

            # Verify CRC
            computed_crc = self._crc32_ieee(usb_frame.payload)
            if computed_crc != usb_frame.crc32:
                self.stats["frames_crc_errors"] += 1
                logger.warning(
                    f"[{self.device_path}] CRC mismatch: expected {usb_frame.crc32:08x}, got {computed_crc:08x}"
                )
                return False

            self.stats["frames_received"] += 1

            # Parse payload based on type
            if usb_frame.payload_type == usb_transport_pb2.USB_PAYLOAD_TYPE_ESP_MESSAGE:
                esp_msg = esp_collector_pb2.EspMessage()
                esp_msg.ParseFromString(usb_frame.payload)
                self.stats["messages_received"] += 1

                # Invoke callback
                if self.message_callback:
                    await self.message_callback(esp_msg)

            else:
                logger.warning(f"Unknown payload type: {usb_frame.payload_type}")

            return True
        except Exception as e:
            self.stats["frames_parse_errors"] += 1
            logger.error(f"[{self.device_path}] Failed to parse frame: {e}")
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
                    logger.error(f"[{self.device_path}] Serial connection not open")
                    break

                try:
                    chunk = await self.reader.read(1024)
                except (serial.SerialException, OSError) as e:
                    logger.error(f"[{self.device_path}] Serial read error: {e}")
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
                        "[%s] USB stats: frames=%d crc_errors=%d parse_errors=%d messages=%d bytes=%d",
                        self.device_path,
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


def get_usb_interface_string(device_path: str) -> str:
    """Return the USB interface string for a tty device if available."""
    try:
        dev_name = Path(device_path).name
        interface_path = Path("/sys/class/tty") / dev_name / "device" / "interface"
        if interface_path.exists():
            return interface_path.read_text().strip()
    except Exception:
        pass
    return ""


def get_usb_device_serial(device_path: str) -> str:
    """Return the USB device serial for a tty device if available."""
    try:
        dev_name = Path(device_path).name
        device_dir = (Path("/sys/class/tty") / dev_name / "device").resolve()
        for candidate in [device_dir / "serial", device_dir.parent / "serial"]:
            if candidate.exists():
                return candidate.read_text().strip()
    except Exception:
        pass
    return ""


def get_usb_bus_port(device_path: str) -> str:
    """Return unique USB bus-port identifier for a tty device.

    This combines bus number and port path to uniquely identify a physical USB device,
    even when multiple devices share the same serial number.

    Returns:
        String like "3-1" or "9-1.1" identifying the physical USB port
    """
    try:
        dev_name = Path(device_path).name
        device_dir = (Path("/sys/class/tty") / dev_name / "device").resolve().parent

        # Read busnum and devpath from USB device sysfs
        busnum_path = device_dir / "busnum"
        devpath_path = device_dir / "devpath"

        if busnum_path.exists() and devpath_path.exists():
            busnum = busnum_path.read_text().strip()
            devpath = devpath_path.read_text().strip()
            return f"{busnum}-{devpath}"
    except Exception:
        pass
    return ""


async def discover_and_group_usb_interfaces() -> dict[str, EspDeviceGroup]:
    """Discover all USB interfaces and group them by physical device.

    Returns:
        Dictionary mapping unique device identifier to EspDeviceGroup.
        Uses bus-port as primary key since USB serial may not be unique.
    """
    devices = await discover_usb_devices()
    groups: dict[str, EspDeviceGroup] = {}

    for device_path in devices:
        interface_string = get_usb_interface_string(device_path)
        usb_serial = get_usb_device_serial(device_path)
        bus_port = get_usb_bus_port(device_path)

        # Use bus-port as primary key (unique per physical USB port)
        # Fall back to USB serial, then device path if bus-port unavailable
        if bus_port:
            group_key = f"bus-port:{bus_port}"
        elif usb_serial:
            group_key = f"serial:{usb_serial}"
        else:
            group_key = f"path:{device_path}"

        # Determine interface type
        if interface_string == "ECG-ESP-DATA":
            interface_type = InterfaceType.DATA
        elif interface_string == "ECG-ESP-LOG":
            interface_type = InterfaceType.LOG
        else:
            interface_type = InterfaceType.UNKNOWN

        # Create interface info
        interface_info = UsbInterfaceInfo(
            device_path=device_path,
            interface_type=interface_type,
            usb_serial=usb_serial,
            interface_string=interface_string,
        )

        # Create or update device group
        if group_key not in groups:
            groups[group_key] = EspDeviceGroup(usb_serial=usb_serial, bus_port=bus_port)

        # Add interface to appropriate slot
        if interface_type == InterfaceType.DATA:
            groups[group_key].data_interface = interface_info
        elif interface_type == InterfaceType.LOG:
            groups[group_key].log_interface = interface_info
        else:
            # Handle unknown interfaces - add as data interface if no data interface exists
            if groups[group_key].data_interface is None:
                groups[group_key].data_interface = interface_info

    return groups


async def probe_usb_device(device_path: str, timeout_s: float = 2.0) -> dict | None:
    """Probe a USB device for a valid CollectorMessage.

    Returns:
        Dict with basic device info if detected, otherwise None.
    """
    reader: asyncio.StreamReader | None = None
    writer: asyncio.StreamWriter | None = None
    buffer = bytearray()
    max_frame_len = 4096

    last_message: dict | None = None

    try:
        reader, writer = await serial_asyncio.open_serial_connection(
            url=device_path,
            baudrate=115200,
        )

        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            try:
                chunk = await asyncio.wait_for(reader.read(1024), timeout=0.2)
            except TimeoutError:
                continue
            if not chunk:
                continue
            buffer.extend(chunk)

            while len(buffer) >= 4:
                frame_length = struct.unpack_from("<I", buffer, 0)[0]
                if frame_length == 0 or frame_length > max_frame_len:
                    buffer.pop(0)
                    continue
                if len(buffer) < 4 + frame_length:
                    break

                frame_bytes = bytes(buffer[4 : 4 + frame_length])
                del buffer[: 4 + frame_length]

                usb_frame = usb_transport_pb2.UsbFrame()
                usb_frame.ParseFromString(frame_bytes)
                computed_crc = zlib.crc32(usb_frame.payload) & 0xFFFFFFFF
                if computed_crc != usb_frame.crc32:
                    continue

                if usb_frame.payload_type != usb_transport_pb2.USB_PAYLOAD_TYPE_ESP_MESSAGE:
                    continue

                esp_msg = esp_collector_pb2.EspMessage()
                esp_msg.ParseFromString(usb_frame.payload)
                msg_type = esp_msg.WhichOneof("message")

                if msg_type == "device_info":
                    info = esp_msg.device_info
                    return {
                        "type": "usb_device_info",
                        "esp_id": info.esp_id,
                        "firmware_version": info.firmware_version,
                        "current_target": info.current_target,
                        "config_required": info.config_required,
                        "polar_connected": info.polar_connected,
                    }

                device_id = None
                if msg_type == "ecg_frame":
                    device_id = esp_msg.ecg_frame.device_id
                elif msg_type == "acc_frame":
                    device_id = esp_msg.acc_frame.device_id

                last_message = {
                    "type": msg_type or "unknown",
                    "device_id": device_id or "",
                }
                continue

        return last_message
    finally:
        if writer:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()
