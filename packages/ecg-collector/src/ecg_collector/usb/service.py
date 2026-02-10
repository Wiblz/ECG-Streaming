"""USB Collector Service - Integrates USB collector with gRPC aggregator."""

import asyncio
import contextlib
import time

from ecg_common.logging import get_logger
from ecg_common.models import SensorFrame, SensorType
from ecg_common.proto import esp_collector_pb2

from ecg_collector.base import DataCollector
from ecg_collector.config import CollectorSettings
from ecg_collector.grpc_client import CollectorGrpcClient
from ecg_collector.usb.collector import UsbCollector, discover_and_group_usb_interfaces
from ecg_collector.usb.errors import UsbConfigNotReadyError
from ecg_collector.usb.inventory import EspInventoryManager
from ecg_collector.usb.pairing import PairingManager

logger = get_logger(__name__)
ble_debug_logger = get_logger("ecg_collector.ble_debug")
EXPECTED_PROTOCOL_VERSION = 1


class MultiUsbCollectorService(DataCollector):
    """Service that forwards multiple USB collectors to a single gRPC client."""

    def __init__(
        self,
        device_paths: list[str],
        settings: CollectorSettings,
    ) -> None:
        """Initialize USB collector service from settings.

        Args:
            device_paths: List of USB device paths to use
            settings: Unified collector settings
        """
        # Get device list for initial registration
        device_list = settings.get_device_list()

        # Extract nicknames from device configs
        device_nicknames = {
            device_id: config.nickname
            for device_id, config in settings.devices.items()
            if config.nickname and config.enabled
        }

        # Create gRPC client
        grpc_client = CollectorGrpcClient(
            collector_id=settings.collector_id,
            aggregator_host=settings.aggregator.host,
            aggregator_port=settings.aggregator.port,
            device_ids=device_list,
            display_name=settings.display_name,
            metadata={
                "type": "usb",
                "device_paths": ",".join(device_paths),
            },
            device_nicknames=device_nicknames,
        )

        # Initialize base class
        super().__init__(grpc_client)

        # Store configuration
        self.collector_id = settings.collector_id
        self.display_name = settings.display_name
        self.device_paths = device_paths
        self.devices = settings.devices
        self.esp_to_device = settings.get_esp_to_device_map()
        self.detect_timeout_s = settings.usb.detect_timeout_s
        self.persist_config = settings.usb.persist_config
        self.default_ecg_sample_rate = settings.usb.ecg_sample_rate
        self.default_acc_sample_rate = settings.usb.acc_sample_rate

        # Initialize runtime state
        self.usb_collectors: dict[str, UsbCollector] = {}
        self.running = False
        self.device_ids: set[str] = set()
        self._usb_tasks: dict[str, asyncio.Task[None]] = {}
        self._discovery_task: asyncio.Task[None] | None = None
        self._grpc_task: asyncio.Task[None] | None = None
        self._discovery_interval_s = 5.0
        self._inventory_prune_interval_s = 15.0
        self._inventory_stale_s = 45.0
        self._last_inventory_prune_ts = 0.0
        self._rejected_device_ids: set[str] = set()
        self._configured_esp_ids: set[str] = set()
        self._unmapped_esp_ids: set[str] = set()
        self._seen_app_versions: set[str] = set()

        # Initialize auto-pairing modules
        self._inventory_manager = EspInventoryManager()
        self._pairing_manager = PairingManager(
            devices=settings.devices,
            default_ecg_sample_rate=settings.usb.ecg_sample_rate,
            default_acc_sample_rate=settings.usb.acc_sample_rate,
            esp_to_device_map=settings.get_esp_to_device_map(),
        )

    def _esp_message_device_id(self, esp_msg: esp_collector_pb2.EspMessage) -> str | None:
        """Extract device ID from ESP message."""
        msg_type = esp_msg.WhichOneof("message")
        if msg_type == "sensor_frame":
            device_id = esp_msg.sensor_frame.device_id
            return str(device_id) if device_id else None
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
        """Check if device ID is allowed to stream data.

        Args:
            device_id: Polar device ID

        Returns:
            True if device is enabled and should stream
        """
        if not device_id:
            return False

        # If device is in our config, check enabled flag
        if device_id in self.devices:
            return self.devices[device_id].enabled

        # If not in config, allow (dynamic discovery)
        return True

    async def _handle_message(
        self,
        esp_msg: esp_collector_pb2.EspMessage,
        usb_collector: UsbCollector | None = None,
        device_path: str | None = None,
    ) -> None:
        """Handle ESP message from USB device."""
        if not self.grpc_client:
            logger.warning("gRPC client not initialized, dropping message")
            return

        msg_type = esp_msg.WhichOneof("message")
        logger.debug("Received ESP message type: %s", msg_type)

        # Update ESP inventory cache
        if device_path and msg_type in ["device_info", "sensor_frame"]:
            self._inventory_manager.update_cache_from_message(esp_msg, device_path)

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
            logger.debug(
                "Received sensor_frame: device_id=%s sensor_type=%s sample_rate=%d",
                esp_msg.sensor_frame.device_id,
                esp_msg.sensor_frame.sensor_type,
                esp_msg.sensor_frame.sample_rate,
            )
            # Convert proto to Python dataclass at the wire boundary
            python_frame = self._proto_to_dataclass(esp_msg.sensor_frame)
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
        """Resolve device configuration for a given ESP32 ID.

        Args:
            esp_id: ESP32 device ID

        Returns:
            Tuple of (device_id, ecg_sample_rate, acc_sample_rate)
            Returns (None, default_ecg, default_acc) if no mapping found
        """
        # Look up which device this ESP is assigned to
        device_id = self.esp_to_device.get(esp_id)
        if not device_id:
            return None, self.default_ecg_sample_rate, self.default_acc_sample_rate

        # Get device config for sample rate overrides
        device_config = self.devices.get(device_id)
        if not device_config:
            # Device in map but not in config (shouldn't happen, but handle gracefully)
            return device_id, self.default_ecg_sample_rate, self.default_acc_sample_rate

        # Use per-device sample rates if specified, otherwise use global defaults
        ecg_rate = device_config.ecg_sample_rate or self.default_ecg_sample_rate
        acc_rate = device_config.acc_sample_rate or self.default_acc_sample_rate

        return device_id, ecg_rate, acc_rate

    async def _handle_usb_device_info(
        self,
        esp_msg: esp_collector_pb2.EspMessage,
        usb_collector: UsbCollector | None,  # noqa: ARG002
    ) -> None:
        """Handle USB device info message from ESP32.

        Note: This method only logs device info. All configuration is handled
        by PairingManager to avoid conflicts between manual and auto-pairing.
        """
        info = esp_msg.device_info
        esp_id = info.esp_id
        if not esp_id:
            return

        logger.info(
            "USB device_info from %s: current_target=%s polar_connected=%s config_required=%s "
            "app=%s idf=%s proto=%s",
            esp_id,
            info.current_target or "(none)",
            info.polar_connected,
            info.config_required,
            info.app_version,
            info.idf_version,
            info.protocol_version,
        )
        if info.app_version:
            self._seen_app_versions.add(info.app_version)
            if len(self._seen_app_versions) > 1:
                logger.warning(
                    "Multiple ESP app versions detected: %s",
                    ", ".join(sorted(self._seen_app_versions)),
                )
        if info.protocol_version != EXPECTED_PROTOCOL_VERSION:
            logger.warning(
                "ESP %s protocol version mismatch: expected=%s got=%s",
                esp_id,
                EXPECTED_PROTOCOL_VERSION,
                info.protocol_version,
            )

        # Check if ESP has a manual mapping (for informational purposes only)
        # Actual configuration is handled by PairingManager
        desired_target, _ecg_rate, _acc_rate = self._resolve_device_config(esp_id)
        if not desired_target and esp_id not in self._unmapped_esp_ids:
            logger.info(
                "USB device %s has no manual mapping - will use auto-pairing",
                esp_id,
            )
            self._unmapped_esp_ids.add(esp_id)

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
            await self._handle_message(msg, usb_collector, device_path)

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
            self.usb_collectors.pop(device_path, None)
            self._inventory_manager.drop_device_path(device_path)
            self._usb_tasks.pop(device_path, None)
            return

        try:
            await run_task
        except Exception as e:
            logger.error("USB collector task error for %s: %s", device_path, e, exc_info=True)
        finally:
            self.usb_collectors.pop(device_path, None)
            self._inventory_manager.drop_device_path(device_path)
            self._usb_tasks.pop(device_path, None)

    async def _discovery_loop(self) -> None:
        """Periodically discover USB data interfaces and start collectors."""
        while self.running:
            try:
                finished_paths = [path for path, task in self._usb_tasks.items() if task.done()]
                for path in finished_paths:
                    self._usb_tasks.pop(path, None)

                now = time.time()
                if now - self._last_inventory_prune_ts >= self._inventory_prune_interval_s:
                    self._inventory_manager.prune_stale(self._inventory_stale_s)
                    self._last_inventory_prune_ts = now

                device_groups = await discover_and_group_usb_interfaces()
                data_paths = [
                    group.data_interface.device_path
                    for group in device_groups.values()
                    if group.data_interface
                ]

                for device_path in data_paths:
                    if device_path not in self._usb_tasks:
                        logger.info("Discovered USB device: %s", device_path)
                        self._usb_tasks[device_path] = asyncio.create_task(
                            self._run_usb_device(device_path)
                        )
            except Exception as e:
                logger.error("USB discovery loop error: %s", e, exc_info=True)

            await asyncio.sleep(self._discovery_interval_s)

    async def _send_esp_config(
        self,
        esp_id: str,
        device_path: str,
        target_device_id: str,
        ecg_rate: int,
        acc_rate: int,
    ) -> None:
        """Send USB config to an ESP (used by pairing manager).

        Raises:
            ValueError: If no collector found for device_path
            Exception: If config send fails
        """
        # Find the collector for this device path
        usb_collector = self.usb_collectors.get(device_path)
        if not usb_collector:
            raise UsbConfigNotReadyError(f"No collector for {device_path}")
        if usb_collector.writer is None or not usb_collector.running:
            raise UsbConfigNotReadyError(f"USB writer not ready for {device_path}")

        config_msg = esp_collector_pb2.UsbConfig(
            esp_id=esp_id,
            target_device_id=target_device_id,
            ecg_sample_rate=ecg_rate,
            acc_sample_rate=acc_rate,
            persist=self.persist_config,
        )

        collector_to_esp_msg = esp_collector_pb2.CollectorToEspMessage()
        collector_to_esp_msg.config.CopyFrom(config_msg)

        # This may raise - let caller handle
        await usb_collector.send_collector_to_esp_message(collector_to_esp_msg)
        self._configured_esp_ids.add(esp_id)
        logger.info(f"Sent config to ESP {esp_id}: target={target_device_id}")

    async def start(self) -> None:
        logger.info("Starting multi-USB collector: %s", self.collector_id)
        self.running = True

        try:
            device_paths = list(dict.fromkeys(self.device_paths))
            if not device_paths:
                logger.warning(
                    "No USB device paths provided; continuing with auto-discovery enabled"
                )

            # Start gRPC client
            self._grpc_task = asyncio.create_task(self.grpc_client.run())

            # Start auto-pairing modules
            self._inventory_manager.start()
            self._pairing_manager.start(
                get_inventory=lambda: self._inventory_manager.esp_inventory,
                get_polars=lambda: self._inventory_manager.available_polars,
                send_config=self._send_esp_config,
            )
            logger.info("Started auto-pairing background loops")

            # Start USB discovery loop
            self._discovery_task = asyncio.create_task(self._discovery_loop())

            for device_path in device_paths:
                self._usb_tasks[device_path] = asyncio.create_task(
                    self._run_usb_device(device_path)
                )

            while self.running:
                if self._grpc_task and self._grpc_task.done():
                    logger.warning("gRPC task ended unexpectedly; collector will keep running")
                    self._grpc_task = asyncio.create_task(self.grpc_client.run())
                await asyncio.sleep(1.0)

        except Exception as e:
            logger.error("Multi-USB collector error: %s", e, exc_info=True)
        finally:
            self.running = False
            await self.stop()

    async def stop(self) -> None:
        logger.info("Stopping multi-USB collector")

        # Stop auto-pairing modules
        await self._inventory_manager.stop()
        await self._pairing_manager.stop()
        logger.info("Stopped auto-pairing background loops")

        if self._discovery_task:
            self._discovery_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._discovery_task
            self._discovery_task = None

        if self._grpc_task:
            self._grpc_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._grpc_task
            self._grpc_task = None

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
    settings: CollectorSettings,
) -> list[MultiUsbCollectorService]:
    """Auto-discover and start a multi-USB collector for all available devices.

    Args:
        settings: Collector settings with aggregator configuration

    Returns:
        List of started MultiUsbCollectorService instances
    """
    # Use smart discovery to only get DATA interfaces
    device_groups = await discover_and_group_usb_interfaces()
    data_devices = [
        group.data_interface.device_path for group in device_groups.values() if group.data_interface
    ]

    if not data_devices:
        logger.warning("No USB data interfaces found")
        return []

    total_devices = len(device_groups)
    log_interfaces = sum(1 for g in device_groups.values() if g.log_interface)
    logger.info(
        f"Found {total_devices} ESP device(s) with {len(data_devices)} data interface(s) "
        f"and {log_interfaces} log interface(s). Using: {data_devices}"
    )

    service = MultiUsbCollectorService(
        device_paths=data_devices,
        settings=settings,
    )
    asyncio.create_task(service.start())
    return [service]
