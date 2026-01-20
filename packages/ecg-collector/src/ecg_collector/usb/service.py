"""USB Collector Service - Integrates USB collector with gRPC aggregator."""

import asyncio
import contextlib
import time

from ecg_common.logging import get_logger
from ecg_common.proto import ecg_streaming_pb2

from ecg_collector.grpc_client import CollectorGrpcClient
from ecg_collector.usb.collector import UsbCollector, discover_usb_devices

logger = get_logger(__name__)


class UsbCollectorService:
    """Service that connects USB collector to gRPC aggregator."""

    def __init__(
        self,
        device_path: str,
        aggregator_host: str = "localhost",
        aggregator_port: int = 50051,
        collector_id: str | None = None,
        display_name: str | None = None,
    ) -> None:
        """Initialize USB collector service.

        Args:
            device_path: Path to USB serial device (e.g., /dev/ttyACM0)
            aggregator_host: Aggregator gRPC host
            aggregator_port: Aggregator gRPC port
            collector_id: Unique collector ID (auto-generated if None)
            display_name: Human-readable collector name
        """
        self.device_path = device_path
        self.aggregator_host = aggregator_host
        self.aggregator_port = aggregator_port
        self.collector_id = collector_id or f"usb-{device_path.replace('/', '-')}"
        self.display_name = display_name or f"USB Collector ({device_path})"

        self.usb_collector: UsbCollector | None = None
        self.grpc_client: CollectorGrpcClient | None = None
        self.running = False

        # Track which device IDs we've seen
        self.device_ids: set[str] = set()

    async def _handle_message(self, collector_msg: ecg_streaming_pb2.CollectorMessage) -> None:
        """Handle incoming CollectorMessage from USB.

        Args:
            collector_msg: Parsed CollectorMessage from ESP32
        """
        if not self.grpc_client:
            logger.warning("gRPC client not initialized, dropping message")
            return

        # Extract device IDs from messages
        msg_type = collector_msg.WhichOneof("message")

        if msg_type == "ecg_batch":
            device_id = collector_msg.ecg_batch.device_id
            if device_id:
                if device_id not in self.device_ids:
                    logger.info(f"USB device discovered from ECG batch: {device_id}")
                self.device_ids.add(device_id)
            now_s = time.time()
            for sample in collector_msg.ecg_batch.samples:
                sample.host_receive_time_s = now_s

        elif msg_type == "acc_batch":
            device_id = collector_msg.acc_batch.device_id
            if device_id:
                if device_id not in self.device_ids:
                    logger.info(f"USB device discovered from ACC batch: {device_id}")
                self.device_ids.add(device_id)
            now_s = time.time()
            for sample in collector_msg.acc_batch.samples:
                sample.host_receive_time_s = now_s

        elif msg_type == "status_update":
            device_id = collector_msg.status_update.device_id
            if device_id:
                self.device_ids.add(device_id)

        # Forward message to aggregator
        try:
            if self.grpc_client and self.device_ids:
                sorted_ids = sorted(self.device_ids)
                if sorted_ids != self.grpc_client.device_ids:
                    self.grpc_client.device_ids = sorted_ids
                    logger.info(f"Sending updated registration with devices: {sorted_ids}")
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
            logger.error(f"Failed to forward message to aggregator: {e}")

    async def start(self) -> None:
        """Start the USB collector service."""
        logger.info(f"Starting USB collector service: {self.collector_id} @ {self.device_path}")
        self.running = True

        try:
            # Initialize gRPC client
            self.grpc_client = CollectorGrpcClient(
                collector_id=self.collector_id,
                aggregator_host=self.aggregator_host,
                aggregator_port=self.aggregator_port,
                device_ids=[],  # Will be populated as we see messages
                display_name=self.display_name,
                metadata={"type": "usb", "device_path": self.device_path},
            )

            # Initialize USB collector
            self.usb_collector = UsbCollector(
                device_path=self.device_path, message_callback=self._handle_message
            )

            # Start gRPC client (will send registration and start streaming)
            grpc_task = asyncio.create_task(self.grpc_client.run())

            # Start USB collector (will read from serial port)
            usb_task = asyncio.create_task(self.usb_collector.run())

            # Wait for either task to complete (or both)
            done, pending = await asyncio.wait(
                [grpc_task, usb_task], return_when=asyncio.FIRST_COMPLETED
            )

            # Cancel remaining tasks
            for task in pending:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

        except Exception as e:
            logger.error(f"USB collector service error: {e}", exc_info=True)
        finally:
            self.running = False
            await self.stop()

    async def stop(self) -> None:
        """Stop the USB collector service."""
        logger.info("Stopping USB collector service")

        if self.usb_collector:
            await self.usb_collector.stop()

        if self.grpc_client:
            await self.grpc_client.disconnect()

    def get_stats(self) -> dict:
        """Get service statistics.

        Returns:
            Dictionary with statistics
        """
        stats = {
            "collector_id": self.collector_id,
            "device_path": self.device_path,
            "running": self.running,
            "device_ids": list(self.device_ids),
        }

        if self.usb_collector:
            stats["usb"] = self.usb_collector.get_stats()

        if self.grpc_client:
            stats["grpc_connected"] = self.grpc_client.connected

        return stats


async def auto_start_usb_collectors(
    aggregator_host: str = "localhost",
    aggregator_port: int = 50051,
) -> list[UsbCollectorService]:
    """Auto-discover and start USB collectors for all available devices.

    Args:
        aggregator_host: Aggregator gRPC host
        aggregator_port: Aggregator gRPC port

    Returns:
        List of started UsbCollectorService instances
    """
    devices = await discover_usb_devices()

    if not devices:
        logger.warning("No USB devices found")
        return []

    logger.info(f"Found {len(devices)} USB device(s): {devices}")

    services = []
    for device_path in devices:
        service = UsbCollectorService(
            device_path=device_path,
            aggregator_host=aggregator_host,
            aggregator_port=aggregator_port,
        )
        services.append(service)
        asyncio.create_task(service.start())

    return services
