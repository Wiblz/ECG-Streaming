"""USB Collector Service - Integrates USB collector with gRPC aggregator."""

import asyncio
import contextlib
import time

from ecg_common.logging import get_logger
from ecg_common.models import SensorFrame, SensorType
from ecg_common.proto import esp_collector_pb2

from ecg_collector.base import DataCollector
from ecg_collector.grpc_client import CollectorGrpcClient
from ecg_collector.usb.collector import UsbCollector, discover_usb_devices

logger = get_logger(__name__)
ble_debug_logger = get_logger("ecg_collector.ble_debug")


class MultiUsbCollectorService(DataCollector):
    """Service that forwards multiple USB collectors to a single gRPC client."""

    def __init__(
        self,
        device_paths: list[str],
        aggregator_host: str = "localhost",
        aggregator_port: int = 50051,
        collector_id: str | None = None,
        display_name: str | None = None,
        allowed_device_ids: list[str] | None = None,
        detect_timeout_s: float = 20.0,
        device_map: dict[str, str | dict[str, object]] | None = None,
        persist_config: bool = True,
        ecg_sample_rate: int = 130,
        acc_sample_rate: int = 100,
    ) -> None:
        """Initialize multi-USB collector service."""
        # Create gRPC client with empty device list (will be updated dynamically)
        self.collector_id = collector_id or "usb-collector"
        self.display_name = display_name or "USB Collector"

        grpc_client = CollectorGrpcClient(
            collector_id=self.collector_id,
            aggregator_host=aggregator_host,
            aggregator_port=aggregator_port,
            device_ids=[],  # Empty initially, updated as devices are discovered
            display_name=self.display_name,
            metadata={
                "type": "usb",
                "device_paths": ",".join(device_paths),
            },
        )

        # Initialize base class
        super().__init__(grpc_client)

        # USB-specific configuration
        self.device_paths = device_paths
        self.allowed_device_ids = set(allowed_device_ids or [])
        self.detect_timeout_s = detect_timeout_s
        self.device_map: dict[str, str | dict[str, object]] = device_map or {}
        self.persist_config = persist_config
        self.ecg_sample_rate = ecg_sample_rate
        self.acc_sample_rate = acc_sample_rate

        self.usb_collectors: dict[str, UsbCollector] = {}
        self.running = False
        self.device_ids: set[str] = set()
        self._usb_tasks: dict[str, asyncio.Task[None]] = {}
        self._rejected_device_ids: set[str] = set()
        self._configured_esp_ids: set[str] = set()
        self._unmapped_esp_ids: set[str] = set()
        self._last_usb_config: dict[str, tuple[str, int, int]] = {}
        self._last_frame_ts: dict[tuple[str, SensorType], int] = {}

    def _esp_message_device_id(self, esp_msg: esp_collector_pb2.EspMessage) -> str | None:
        """Extract device ID from ESP message."""
        msg_type = esp_msg.WhichOneof("message")
        if msg_type == "sensor_frame":
            return esp_msg.sensor_frame.device_id
        return None

    def _proto_to_dataclass(self, proto_frame: esp_collector_pb2.SensorFrame) -> SensorFrame:
        """Convert proto SensorFrame to Python SensorFrame dataclass.

        This is the deserialization boundary - proto types should not leak beyond this point.
        Captures the actual collector receive time (wall clock epoch time) for time alignment.
        Preserves all three timestamps: polar_clock_us, receiver_clock_us, and wall_clock_us.
        """
        sensor_type_map = {
            esp_collector_pb2.SENSOR_TYPE_ECG: SensorType.ECG,
            esp_collector_pb2.SENSOR_TYPE_ACCELEROMETER: SensorType.ACCELEROMETER,
        }

        # Capture wall clock time (epoch time in microseconds)
        wall_clock_us = int(time.time() * 1_000_000)

        return SensorFrame(
            device_id=proto_frame.device_id,
            sensor_type=sensor_type_map[proto_frame.sensor_type],
            polar_clock_us=proto_frame.polar_clock_us,
            receiver_clock_us=proto_frame.receiver_clock_us,  # Keep ESP32 boot time
            wall_clock_us=wall_clock_us,  # Add collector wall clock time
            sample_rate=proto_frame.sample_rate,
            raw_data=proto_frame.raw_data,
        )

    def _device_id_allowed(self, device_id: str | None) -> bool:
        if not self.allowed_device_ids:
            return True
        return bool(device_id) and device_id in self.allowed_device_ids

    async def _handle_message(
        self,
        esp_msg: esp_collector_pb2.EspMessage,
        usb_collector: UsbCollector | None = None,
    ) -> None:
        """Handle ESP message from USB device."""
        if not self.grpc_client:
            logger.warning("gRPC client not initialized, dropping message")
            return

        msg_type = esp_msg.WhichOneof("message")

        # Handle device info
        if msg_type == "device_info":
            await self._handle_usb_device_info(esp_msg, usb_collector)
            return

        # Handle BLE debug
        if msg_type == "ble_debug":
            dbg = esp_msg.ble_debug
            ble_debug_logger.info(
                "ble_debug",
                extra={
                    "ble_debug": {
                        "device_id": dbg.device_id or "",
                        "frame_type_hex": f"0x{dbg.frame_type:02X}",
                        "pmd_type_hex": f"0x{dbg.pmd_type:02X}",
                        "notif_len": dbg.notif_len,
                        "sample_count": dbg.sample_count,
                        "polar_clock_us": dbg.polar_clock_us,
                        "interval_us": dbg.interval_us,
                        "notification_index": dbg.notification_index,
                        "conn_interval_ms": dbg.conn_interval_ms,
                        "mtu": dbg.mtu,
                    }
                },
            )
            return

        # Handle config ack
        if msg_type == "config_ack":
            ack = esp_msg.config_ack
            logger.info(
                "USB config ack from %s: %s (accepted=%s)",
                ack.esp_id,
                ack.message or "ok",
                ack.accepted,
            )
            return

        # Handle ECG/ACC frames - convert to batches and forward
        device_id = self._esp_message_device_id(esp_msg)
        if device_id and not self._device_id_allowed(device_id):
            if device_id not in self._rejected_device_ids:
                logger.warning("Ignoring USB device ID not in allowlist: %s", device_id)
                self._rejected_device_ids.add(device_id)
            return

        if device_id:
            if device_id not in self.device_ids:
                logger.info("USB device discovered from stream: %s", device_id)
            self.device_ids.add(device_id)

        # Convert sensor frame: proto → Python dataclass → batch message
        if msg_type == "sensor_frame":
            # Convert proto to Python dataclass at the wire boundary
            python_frame = self._proto_to_dataclass(esp_msg.sensor_frame)
            last_key = (python_frame.device_id, python_frame.sensor_type)
            last_ts = self._last_frame_ts.get(last_key)
            if last_ts is not None:
                if python_frame.sensor_type == SensorType.ECG:
                    sample_size = 3
                else:
                    sample_size = 6
                sample_count = len(python_frame.raw_data) // sample_size
                expected_span_us = (
                    int((sample_count - 1) * 1_000_000 / python_frame.sample_rate)
                    if sample_count > 1 and python_frame.sample_rate > 0
                    else 0
                )
                delta_us = python_frame.polar_clock_us - last_ts
                gap_threshold_us = max(500_000, expected_span_us * 2)
                if delta_us > gap_threshold_us:
                    logger.warning(
                        "USB gap detected %s %s: delta_us=%d expected_span_us=%d samples=%d",
                        python_frame.device_id,
                        python_frame.sensor_type.name,
                        delta_us,
                        expected_span_us,
                        sample_count,
                    )
            self._last_frame_ts[last_key] = python_frame.polar_clock_us

            try:
                # Update registration if device list changed
                if self.device_ids:
                    sorted_ids = sorted(self.device_ids)
                    if sorted_ids != self.grpc_client.device_ids:
                        from ecg_common.proto import collector_aggregator_pb2

                        self.grpc_client.device_ids = sorted_ids
                        logger.info("Sending updated registration with devices: %s", sorted_ids)
                        registration = collector_aggregator_pb2.CollectorRegistration(
                            collector_id=self.grpc_client.collector_id,
                            device_ids=sorted_ids,
                            display_name=self.grpc_client.display_name,
                            metadata=self.grpc_client.metadata,
                        )
                        reg_msg = collector_aggregator_pb2.CollectorMessage()
                        reg_msg.registration.CopyFrom(registration)
                        await self.grpc_client.send_message(reg_msg)

                # Send frame using base class method (handles conversion + sending)
                await self.send_frame_batch(python_frame)
            except Exception as e:
                logger.error("Failed to forward message to aggregator: %s", e)

    def _resolve_device_config(self, esp_id: str) -> tuple[str | None, int, int]:
        mapping = self.device_map.get(esp_id)
        if mapping is None:
            return None, self.ecg_sample_rate, self.acc_sample_rate
        if isinstance(mapping, str):
            return mapping, self.ecg_sample_rate, self.acc_sample_rate
        device_id = mapping.get("device_id")
        if not isinstance(device_id, str) or not device_id:
            return None, self.ecg_sample_rate, self.acc_sample_rate

        ecg_rate_value = mapping.get("ecg_sample_rate", self.ecg_sample_rate)
        acc_rate_value = mapping.get("acc_sample_rate", self.acc_sample_rate)

        ecg_rate = self.ecg_sample_rate
        if isinstance(ecg_rate_value, int):
            ecg_rate = ecg_rate_value
        elif isinstance(ecg_rate_value, str):
            try:
                ecg_rate = int(ecg_rate_value)
            except ValueError:
                ecg_rate = self.ecg_sample_rate

        acc_rate = self.acc_sample_rate
        if isinstance(acc_rate_value, int):
            acc_rate = acc_rate_value
        elif isinstance(acc_rate_value, str):
            try:
                acc_rate = int(acc_rate_value)
            except ValueError:
                acc_rate = self.acc_sample_rate

        return device_id, ecg_rate, acc_rate

    async def _handle_usb_device_info(
        self,
        esp_msg: esp_collector_pb2.EspMessage,
        usb_collector: UsbCollector | None,
    ) -> None:
        """Handle USB device info message from ESP32."""
        info = esp_msg.device_info
        esp_id = info.esp_id
        if not esp_id:
            return

        desired_target, ecg_rate, acc_rate = self._resolve_device_config(esp_id)
        if not desired_target:
            if esp_id not in self._unmapped_esp_ids:
                logger.info("USB device %s has no mapping; add to usb.device_map", esp_id)
                self._unmapped_esp_ids.add(esp_id)
            return

        desired_config = (desired_target, ecg_rate, acc_rate)
        if (
            esp_id in self._configured_esp_ids
            and info.current_target == desired_target
            and self._last_usb_config.get(esp_id) == desired_config
        ):
            return

        if not usb_collector:
            logger.warning("No USB collector available to configure %s", esp_id)
            return

        config_msg = esp_collector_pb2.UsbConfig(
            esp_id=esp_id,
            target_device_id=desired_target,
            ecg_sample_rate=ecg_rate,
            acc_sample_rate=acc_rate,
            persist=self.persist_config,
        )
        collector_to_esp_msg = esp_collector_pb2.CollectorToEspMessage()
        collector_to_esp_msg.config.CopyFrom(config_msg)

        try:
            await usb_collector.send_collector_to_esp_message(collector_to_esp_msg)
            self._configured_esp_ids.add(esp_id)
            self._last_usb_config[esp_id] = desired_config
            logger.info("Sent USB config to %s -> %s", esp_id, desired_target)
        except Exception as e:
            logger.error("Failed sending USB config to %s: %s", esp_id, e)

    async def _run_usb_device(self, device_path: str) -> None:
        first_message = asyncio.Event()

        async def _callback(msg: esp_collector_pb2.EspMessage) -> None:
            if not first_message.is_set():
                msg_type = msg.WhichOneof("message")
                if msg_type == "device_info":
                    first_message.set()
                else:
                    device_id = self._esp_message_device_id(msg)
                    if self._device_id_allowed(device_id):
                        first_message.set()
            await self._handle_message(msg, usb_collector)

        usb_collector = UsbCollector(device_path=device_path, message_callback=_callback)
        self.usb_collectors[device_path] = usb_collector
        run_task = asyncio.create_task(usb_collector.run())

        try:
            await asyncio.wait_for(first_message.wait(), timeout=self.detect_timeout_s)
        except TimeoutError:
            logger.warning(
                "No valid USB data on %s within %.1fs; skipping device",
                device_path,
                self.detect_timeout_s,
            )
            await usb_collector.stop()
            run_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await run_task
            return

        try:
            await run_task
        except Exception as e:
            logger.error("USB collector task error for %s: %s", device_path, e, exc_info=True)

    async def start(self) -> None:
        logger.info("Starting multi-USB collector: %s", self.collector_id)
        self.running = True

        try:
            device_paths = list(dict.fromkeys(self.device_paths))
            if not device_paths:
                logger.error("No USB device paths provided")
                return

            # Start gRPC client
            grpc_task = asyncio.create_task(self.grpc_client.run())

            for device_path in device_paths:
                self._usb_tasks[device_path] = asyncio.create_task(
                    self._run_usb_device(device_path)
                )

            await grpc_task

        except Exception as e:
            logger.error("Multi-USB collector error: %s", e, exc_info=True)
        finally:
            self.running = False
            await self.stop()

    async def stop(self) -> None:
        logger.info("Stopping multi-USB collector")

        for task in self._usb_tasks.values():
            task.cancel()
        for task in self._usb_tasks.values():
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._usb_tasks.clear()

        for collector in self.usb_collectors.values():
            await collector.stop()
        self.usb_collectors.clear()

        if self.grpc_client:
            await self.grpc_client.disconnect()


async def auto_start_usb_collectors(
    aggregator_host: str = "localhost",
    aggregator_port: int = 50051,
) -> list[MultiUsbCollectorService]:
    """Auto-discover and start a multi-USB collector for all available devices.

    Args:
        aggregator_host: Aggregator gRPC host
        aggregator_port: Aggregator gRPC port

    Returns:
        List of started MultiUsbCollectorService instances
    """
    devices = await discover_usb_devices()

    if not devices:
        logger.warning("No USB devices found")
        return []

    logger.info(f"Found {len(devices)} USB device(s): {devices}")

    service = MultiUsbCollectorService(
        device_paths=devices,
        aggregator_host=aggregator_host,
        aggregator_port=aggregator_port,
    )
    asyncio.create_task(service.start())
    return [service]
