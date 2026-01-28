"""Base class for data collectors that forward frames to aggregator.

This module contains the shared logic for both BLE and USB collectors,
extracting common patterns like frame conversion, status updates, and gRPC communication.
"""

import time
from abc import ABC, abstractmethod

from ecg_common.logging import get_logger
from ecg_common.models import DeviceStatus, SensorFrame, SensorType
from ecg_common.proto import collector_aggregator_pb2, common_pb2

from ecg_collector.grpc_client import CollectorGrpcClient
from ecg_collector.polar import parse_acc_frame, parse_ecg_frame

logger = get_logger(__name__)


class DataCollector(ABC):
    """Base class for data collectors that forward frames to aggregator.

    Provides shared logic for:
    - Frame to batch conversion
    - Device status updates
    - gRPC communication

    Subclasses implement specific data source logic (BLE, USB, etc.)
    """

    def __init__(self, grpc_client: CollectorGrpcClient):
        """Initialize the data collector.

        Args:
            grpc_client: Configured gRPC client for aggregator communication
        """
        self.grpc_client = grpc_client
        self._device_statuses: dict[str, DeviceStatus] = {}

    async def send_frame_batch(self, frame: SensorFrame) -> None:
        """Convert frame to batch and send to aggregator.

        This is the unified path for both BLE and USB collectors.
        Parses raw PMD data into structured samples and sends to aggregator.

        Args:
            frame: Python SensorFrame dataclass with raw PMD data
        """
        try:
            # Parse raw PMD data into structured samples
            if frame.sensor_type == SensorType.ECG:
                samples = parse_ecg_frame(
                    frame.raw_data,
                    frame.polar_clock_us,
                    frame.sample_rate,
                    frame.device_id,
                    frame.wall_clock_us,
                    frame.receiver_clock_us,
                )
                batch = collector_aggregator_pb2.ECGBatch(
                    device_id=frame.device_id,
                    wall_clock_us=frame.wall_clock_us,
                    batch_timestamp_us=int(time.time() * 1_000_000),
                    sample_rate=frame.sample_rate,
                    samples=samples,
                )
                msg = collector_aggregator_pb2.CollectorMessage()
                msg.ecg_batch.CopyFrom(batch)

            elif frame.sensor_type == SensorType.ACCELEROMETER:
                samples = parse_acc_frame(
                    frame.raw_data,
                    frame.polar_clock_us,
                    frame.sample_rate,
                    frame.device_id,
                    frame.wall_clock_us,
                    frame.receiver_clock_us,
                )
                batch = collector_aggregator_pb2.AccelerometerBatch(
                    device_id=frame.device_id,
                    wall_clock_us=frame.wall_clock_us,
                    batch_timestamp_us=int(time.time() * 1_000_000),
                    sample_rate=frame.sample_rate,
                    samples=samples,
                )
                msg = collector_aggregator_pb2.CollectorMessage()
                msg.acc_batch.CopyFrom(batch)

            else:
                raise ValueError(f"Unknown sensor type: {frame.sensor_type}")

            # Send to aggregator
            await self.grpc_client.send_message(msg)

        except Exception as e:
            logger.error(f"Failed to convert/send frame from {frame.device_id}: {e}")
            raise

    async def send_status_update(self, device_id: str, status: DeviceStatus) -> None:
        """Send device status update to aggregator.

        Only sends if status has changed to avoid spamming aggregator.

        Args:
            device_id: Device ID
            status: Device status
        """
        # Only send if status changed
        if self._device_statuses.get(device_id) == status:
            return

        self._device_statuses[device_id] = status

        status_map = {
            DeviceStatus.UNKNOWN: common_pb2.DEVICE_STATUS_UNKNOWN,
            DeviceStatus.DISCONNECTED: common_pb2.DEVICE_STATUS_DISCONNECTED,
            DeviceStatus.CONNECTING: common_pb2.DEVICE_STATUS_CONNECTING,
            DeviceStatus.CONNECTED: common_pb2.DEVICE_STATUS_CONNECTED,
            DeviceStatus.STREAMING: common_pb2.DEVICE_STATUS_STREAMING,
            DeviceStatus.ERROR: common_pb2.DEVICE_STATUS_ERROR,
        }

        pb_status = status_map.get(status, common_pb2.DEVICE_STATUS_UNKNOWN)
        status_update = collector_aggregator_pb2.DeviceStatusUpdate(
            device_id=device_id,
            status=pb_status,
        )
        msg = collector_aggregator_pb2.CollectorMessage()
        msg.status_update.CopyFrom(status_update)
        await self.grpc_client.send_message(msg)
        logger.info(f"Sent status update for {device_id}: {status.name}")

    @abstractmethod
    async def start(self) -> None:
        """Start the collector.

        Subclasses implement their specific startup logic:
        - BLE: Initialize adapters, start device state manager, monitor loop
        - USB: Discover devices, start USB collectors, handle config protocol
        """
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Stop the collector.

        Subclasses implement their specific shutdown logic.
        """
        pass
