"""Buffer query application service."""

from ecg_aggregator.application.dto.buffer import (
    BufferedAccelerometerSampleDTO,
    BufferedECGSampleDTO,
)
from ecg_aggregator.domain.realtime import BufferStatsSnapshot
from ecg_aggregator.infrastructure.realtime.buffers import (
    AccelerometerDataBuffer,
    ECGDataBuffer,
)


class BufferQueryService:
    """Read-oriented queries over the in-memory realtime buffers."""

    def __init__(
        self,
        *,
        ecg_buffer: ECGDataBuffer,
        acc_buffer: AccelerometerDataBuffer,
    ) -> None:
        self.ecg_buffer = ecg_buffer
        self.acc_buffer = acc_buffer

    def get_ecg_buffer_stats(self) -> BufferStatsSnapshot:
        """Return ECG buffer statistics."""
        return BufferStatsSnapshot.model_validate(self.ecg_buffer.get_stats())

    def get_latest_ecg_samples(self) -> dict[str, BufferedECGSampleDTO]:
        """Return the latest ECG sample for each device."""
        return {
            device_id: BufferedECGSampleDTO.model_validate(sample)
            for device_id, sample in self.ecg_buffer.get_latest_by_device().items()
        }

    def get_acc_buffer_stats(self) -> BufferStatsSnapshot:
        """Return accelerometer buffer statistics."""
        return BufferStatsSnapshot.model_validate(self.acc_buffer.get_stats())

    def get_latest_acc_samples(self) -> dict[str, BufferedAccelerometerSampleDTO]:
        """Return the latest accelerometer sample for each device."""
        return {
            device_id: BufferedAccelerometerSampleDTO.model_validate(sample)
            for device_id, sample in self.acc_buffer.get_latest_by_device().items()
        }
