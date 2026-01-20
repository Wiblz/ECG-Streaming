"""USB Collector Service - Integrates USB collector with gRPC aggregator."""

import asyncio
import contextlib
import time

from ecg_common.logging import get_logger
from ecg_common.proto import ecg_streaming_pb2

from ecg_collector.grpc_client import CollectorGrpcClient
from ecg_collector.usb.collector import UsbCollector, discover_usb_devices

logger = get_logger(__name__)


class MultiUsbCollectorService:
    """Service that forwards multiple USB collectors to a single gRPC client."""

    def __init__(
        self,
        device_paths: list[str],
        aggregator_host: str = "localhost",
        aggregator_port: int = 50051,
        collector_id: str | None = None,
        display_name: str | None = None,
        allowed_device_ids: list[str] | None = None,
        detect_timeout_s: float = 10.0,
    ) -> None:
        """Initialize multi-USB collector service."""
        self.device_paths = device_paths
        self.aggregator_host = aggregator_host
        self.aggregator_port = aggregator_port
        self.collector_id = collector_id or "usb-collector"
        self.display_name = display_name or "USB Collector"
        self.allowed_device_ids = set(allowed_device_ids or [])
        self.detect_timeout_s = detect_timeout_s

        self.usb_collectors: dict[str, UsbCollector] = {}
        self.grpc_client: CollectorGrpcClient | None = None
        self.running = False
        self.device_ids: set[str] = set()
        self._usb_tasks: dict[str, asyncio.Task[None]] = {}
        self._rejected_device_ids: set[str] = set()

    def _message_device_id(self, collector_msg: ecg_streaming_pb2.CollectorMessage) -> str | None:
        msg_type = collector_msg.WhichOneof("message")
        if msg_type == "ecg_batch":
            return collector_msg.ecg_batch.device_id
        if msg_type == "acc_batch":
            return collector_msg.acc_batch.device_id
        if msg_type == "status_update":
            return collector_msg.status_update.device_id
        return None

    def _device_id_allowed(self, device_id: str | None) -> bool:
        if not self.allowed_device_ids:
            return True
        return bool(device_id) and device_id in self.allowed_device_ids

    async def _handle_message(self, collector_msg: ecg_streaming_pb2.CollectorMessage) -> None:
        if not self.grpc_client:
            logger.warning("gRPC client not initialized, dropping message")
            return

        device_id = self._message_device_id(collector_msg)
        if device_id and not self._device_id_allowed(device_id):
            if device_id not in self._rejected_device_ids:
                logger.warning("Ignoring USB device ID not in allowlist: %s", device_id)
                self._rejected_device_ids.add(device_id)
            return

        if device_id:
            if device_id not in self.device_ids:
                logger.info("USB device discovered from stream: %s", device_id)
            self.device_ids.add(device_id)

        msg_type = collector_msg.WhichOneof("message")
        if msg_type == "ecg_batch":
            now_s = time.time()
            for sample in collector_msg.ecg_batch.samples:
                sample.host_receive_time_s = now_s
        elif msg_type == "acc_batch":
            now_s = time.time()
            for sample in collector_msg.acc_batch.samples:
                sample.host_receive_time_s = now_s

        try:
            if self.device_ids:
                sorted_ids = sorted(self.device_ids)
                if sorted_ids != self.grpc_client.device_ids:
                    self.grpc_client.device_ids = sorted_ids
                    logger.info("Sending updated registration with devices: %s", sorted_ids)
                    registration = ecg_streaming_pb2.CollectorRegistration(
                        collector_id=self.grpc_client.collector_id,
                        device_ids=sorted_ids,
                        display_name=self.grpc_client.display_name,
                        metadata=self.grpc_client.metadata,
                    )
                    reg_msg = ecg_streaming_pb2.CollectorMessage()
                    reg_msg.registration.CopyFrom(registration)
                    await self.grpc_client.send_message(reg_msg)
            await self.grpc_client.send_message(collector_msg)
        except Exception as e:
            logger.error("Failed to forward message to aggregator: %s", e)

    async def _run_usb_device(self, device_path: str) -> None:
        first_message = asyncio.Event()

        async def _callback(msg: ecg_streaming_pb2.CollectorMessage) -> None:
            if not first_message.is_set():
                device_id = self._message_device_id(msg)
                if self._device_id_allowed(device_id):
                    first_message.set()
            await self._handle_message(msg)

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

            self.grpc_client = CollectorGrpcClient(
                collector_id=self.collector_id,
                aggregator_host=self.aggregator_host,
                aggregator_port=self.aggregator_port,
                device_ids=[],
                display_name=self.display_name,
                metadata={
                    "type": "usb",
                    "device_paths": ",".join(device_paths),
                },
            )

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
