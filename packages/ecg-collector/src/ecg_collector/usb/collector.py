"""USB Collector for ESP32-based devices.

Reads protobuf messages from USB serial port using length-prefixed UsbFrame protocol.
"""

import asyncio
import contextlib
import struct
import time
import zlib
from collections import deque
from collections.abc import Callable, Coroutine
from pathlib import Path

import serial
import serial_asyncio
from ecg_common.logging import get_logger
from ecg_common.proto import esp_collector_pb2, usb_transport_pb2
from google.protobuf.message import Message

from .models import (
    EspDeviceGroup,
    EspDeviceInfo,
    InterfaceType,
    ProbePartialInfo,
    ProbeStatus,
    UsbCollectorStats,
    UsbInterfaceInfo,
)

logger = get_logger(__name__)


class UsbCollector:
    """Collects data from ESP32 device via USB serial port."""

    def __init__(
        self,
        device_path: str,
        baudrate: int = 115200,
        message_callback: Callable[[Message], Coroutine[None, None, None]] | None = None,
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
        self.stats = UsbCollectorStats()
        self._tx_seq = 0
        self._rx_seq: int | None = None
        self.frames_dropped = 0
        self._last_gap_log = 0.0

        # Throughput tracking with rolling window
        self._throughput_window_s = 10.0  # 10 second rolling window
        self._throughput_samples: deque[tuple[float, int]] = deque()
        self._bus_port = get_usb_bus_port(device_path)
        self._esp_id: str | None = None  # Track ESP32 ID from device_info

    async def connect(self) -> None:
        """Open serial port connection."""
        try:
            self.reader, self.writer = await serial_asyncio.open_serial_connection(
                url=self.device_path,
                baudrate=self.baudrate,
            )
            self._rx_seq = None
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

    def _track_rx_seq(self, seq: int) -> None:
        """Detect gaps in received UsbFrame seq (fixed32, wraps at 2**32)."""
        if self._rx_seq is not None:
            expected = (self._rx_seq + 1) & 0xFFFFFFFF
            gap = (seq - expected) & 0xFFFFFFFF
            if gap == 0:
                pass
            elif gap < 0x80000000:
                self.frames_dropped += gap
                now = time.monotonic()
                if now - self._last_gap_log >= 1.0:
                    self._last_gap_log = now
                    logger.warning(
                        f"[{self.device_path}] USB frame seq gap: expected {expected}, got {seq} "
                        f"({gap} frames dropped, {self.frames_dropped} total)"
                    )
            else:
                # Seq went backwards: device rebooted and restarted at 0
                logger.info(f"[{self.device_path}] USB frame seq reset: {self._rx_seq} -> {seq}")
        self._rx_seq = seq

    async def _process_frame(self, frame_bytes: bytes) -> bool:
        """Parse and process a UsbFrame.

        Args:
            frame_bytes: Serialized UsbFrame protobuf
        """
        message: Message | None = None
        try:
            # Parse UsbFrame
            usb_frame = usb_transport_pb2.UsbFrame()
            usb_frame.ParseFromString(frame_bytes)

            # Verify CRC
            computed_crc = self._crc32_ieee(usb_frame.payload)
            if computed_crc != usb_frame.crc32:
                self.stats.frames_crc_errors += 1
                logger.warning(
                    f"[{self.device_path}] CRC mismatch: expected {usb_frame.crc32:08x}, got {computed_crc:08x}"
                )
                return False

            self._track_rx_seq(usb_frame.seq)
            self.stats.frames_received += 1

            # Parse payload based on type
            if usb_frame.payload_type == usb_transport_pb2.USB_PAYLOAD_TYPE_ESP_MESSAGE:
                esp_msg = esp_collector_pb2.EspMessage()
                esp_msg.ParseFromString(usb_frame.payload)
                self.stats.messages_received += 1

                # Track ESP ID from device_info messages
                if esp_msg.HasField("device_info"):
                    self._esp_id = esp_msg.device_info.esp_id

                message = esp_msg
            elif usb_frame.payload_type == usb_transport_pb2.USB_PAYLOAD_TYPE_ESP_DISCOVERY_MESSAGE:
                discovery_msg = esp_collector_pb2.EspDiscoveryMessage()
                discovery_msg.ParseFromString(usb_frame.payload)
                self.stats.messages_received += 1

                message = discovery_msg
            else:
                logger.warning(f"Unknown payload type: {usb_frame.payload_type}")
        except Exception as e:
            self.stats.frames_parse_errors += 1
            logger.error(f"[{self.device_path}] Failed to parse frame: {e}")
            return False

        if message is not None and self.message_callback:
            try:
                await self.message_callback(message)
            except Exception as e:
                logger.error(f"[{self.device_path}] Message callback error: {e}", exc_info=True)

        return True

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
                    chunk = await asyncio.wait_for(self.reader.read(1024), timeout=1.0)
                except TimeoutError:
                    continue
                except (serial.SerialException, OSError) as e:
                    logger.error(f"[{self.device_path}] Serial read error: {e}")
                    break
                if not chunk:
                    logger.error(f"[{self.device_path}] Serial connection closed (EOF)")
                    break

                buffer.extend(chunk)
                self.stats.bytes_received += len(chunk)

                # Record sample for throughput calculation
                now = time.monotonic()
                self._throughput_samples.append((now, self.stats.bytes_received))

                # Remove samples outside rolling window
                cutoff_time = now - self._throughput_window_s
                while self._throughput_samples and self._throughput_samples[0][0] < cutoff_time:
                    self._throughput_samples.popleft()

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
                    throughput_bps = self._calculate_throughput_bps()

                    # Use bus-port identifier if available, otherwise fall back to device path
                    connection_id = (
                        f"bus-port:{self._bus_port}" if self._bus_port else self.device_path
                    )

                    # Include ESP ID if known
                    esp_info = f" esp_id={self._esp_id}" if self._esp_id else ""

                    logger.info(
                        "[%s] USB stats: frames=%d dropped=%d crc_errors=%d parse_errors=%d messages=%d bytes=%d throughput=%.1f bytes/sec%s",
                        connection_id,
                        self.stats.frames_received,
                        self.frames_dropped,
                        self.stats.frames_crc_errors,
                        self.stats.frames_parse_errors,
                        self.stats.messages_received,
                        self.stats.bytes_received,
                        throughput_bps,
                        esp_info,
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

    def get_stats(self) -> dict[str, int]:
        """Get collector statistics.

        Returns:
            Dictionary with statistics
        """
        stats = self.stats.to_dict()
        stats["frames_dropped"] = self.frames_dropped
        return stats

    def _calculate_throughput_bps(self) -> float:
        """Calculate rolling average throughput in bytes per second.

        Returns:
            Bytes per second over the rolling window, or 0 if insufficient data
        """
        if len(self._throughput_samples) < 2:
            return 0.0

        # Get oldest and newest samples
        oldest_time, oldest_bytes = self._throughput_samples[0]
        newest_time, newest_bytes = self._throughput_samples[-1]

        time_diff = newest_time - oldest_time
        if time_diff <= 0:
            return 0.0

        bytes_diff = newest_bytes - oldest_bytes
        return bytes_diff / time_diff


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


async def probe_usb_groups(
    device_groups: dict[str, EspDeviceGroup],
    timeout_s: float = 12.0,
    on_update: Callable[[str, EspDeviceGroup], None] | None = None,
) -> None:
    """Probe USB device groups concurrently.

    Probes all device groups in-place, updating their probe_status, device_info,
    partial_info, and error_message fields. Optionally calls a callback after each
    state change with the group key and updated group object.

    Args:
        device_groups: Dictionary of device groups to probe (modified in-place)
        timeout_s: Probe timeout per device in seconds
        on_update: Optional callback invoked when any device state changes.
                   Receives (group_key: str, group: EspDeviceGroup)
    """

    async def probe_device_group(group_key: str, group: EspDeviceGroup) -> None:
        """Probe a single device group's data interface."""
        if not group.data_interface:
            return

        # Reset state before probing (important for reusability in long-lived processes)
        group.probe_status = ProbeStatus.DISCOVERED
        group.device_info = None
        group.partial_info = None
        group.error_message = None
        if on_update:
            on_update(group_key, group)

        # Update to probing state
        group.probe_status = ProbeStatus.PROBING
        if on_update:
            on_update(group_key, group)

        try:
            device_info, partial_info = await probe_usb_device(
                group.data_interface.device_path, timeout_s=timeout_s
            )
            if device_info:
                group.device_info = device_info
                group.probe_status = ProbeStatus.RECEIVED
            else:
                group.probe_status = ProbeStatus.TIMEOUT
                group.partial_info = partial_info  # May be None if no messages seen
        except Exception as e:
            group.probe_status = ProbeStatus.ERROR
            group.error_message = str(e)[:50]  # Truncate error message
        finally:
            if on_update:
                on_update(group_key, group)

    # Probe all device groups concurrently
    probe_tasks = [
        probe_device_group(group_key, group)
        for group_key, group in device_groups.items()
        if group.data_interface
    ]

    if probe_tasks:
        await asyncio.gather(*probe_tasks)


async def probe_usb_device(
    device_path: str, timeout_s: float = 2.0
) -> tuple[EspDeviceInfo | None, ProbePartialInfo | None]:
    """Probe a USB device for a valid CollectorMessage.

    Returns:
        Tuple of (device_info, partial_info):
        - device_info: Full EspDeviceInfo if device_info message received
        - partial_info: Partial data if timeout with other message types seen
        - (None, None): If no valid messages received at all
    """
    reader: asyncio.StreamReader | None = None
    writer: asyncio.StreamWriter | None = None
    buffer = bytearray()
    max_frame_len = 4096

    last_message: dict | None = None

    try:
        logger.info(f"Probing USB device: {device_path} (timeout={timeout_s}s)")
        reader, writer = await serial_asyncio.open_serial_connection(
            url=device_path,
            baudrate=115200,
        )
        logger.debug(f"Opened serial connection to {device_path}")

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

                try:
                    usb_frame = usb_transport_pb2.UsbFrame()
                    usb_frame.ParseFromString(frame_bytes)
                except Exception:
                    buffer.pop(0)
                    continue

                del buffer[: 4 + frame_length]

                computed_crc = zlib.crc32(usb_frame.payload) & 0xFFFFFFFF
                if computed_crc != usb_frame.crc32:
                    continue

                if usb_frame.payload_type != usb_transport_pb2.USB_PAYLOAD_TYPE_ESP_MESSAGE:
                    continue

                try:
                    esp_msg = esp_collector_pb2.EspMessage()
                    esp_msg.ParseFromString(usb_frame.payload)
                except Exception:
                    continue
                msg_type = esp_msg.WhichOneof("message")

                if msg_type == "device_info":
                    info = esp_msg.device_info
                    logger.info(
                        f"Probed {device_path}: ESP_ID={info.esp_id}, target={info.current_target or '<unassigned>'}, "
                        f"polar={'connected' if info.polar_connected else 'disconnected'}, "
                        f"config={'required' if info.config_required else 'ok'}"
                    )
                    device_info = EspDeviceInfo(
                        esp_id=info.esp_id,
                        app_version=info.app_version,
                        idf_version=info.idf_version,
                        protocol_version=info.protocol_version,
                        current_target=info.current_target if info.current_target else None,
                        config_required=info.config_required,
                        polar_connected=info.polar_connected,
                        scanner_active=info.scanner_active,
                        scanner_request_id=info.scanner_request_id,
                        polar_battery_known=info.polar_battery_known,
                        polar_battery_percent=info.polar_battery_percent,
                    )
                    return (device_info, None)

                device_id = None
                if msg_type == "sensor_frame":
                    device_id = esp_msg.sensor_frame.device_id

                last_message = {
                    "type": msg_type or "unknown",
                    "device_id": device_id or "",
                }
                continue

        # Timeout reached
        if last_message:
            logger.warning(
                f"Probe timeout for {device_path}: received {last_message['type']} messages but no device_info"
            )
            partial = ProbePartialInfo(
                last_message_type=last_message["type"], device_id=last_message.get("device_id")
            )
            return (None, partial)
        else:
            logger.warning(f"Probe timeout for {device_path}: no valid messages received")
            return (None, None)

    except Exception as e:
        logger.error(f"Failed to probe {device_path}: {type(e).__name__}: {e}")
        raise

    finally:
        if writer:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()
