"""Time alignment engine for synchronizing device timestamps."""

import time
from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np
from ecg_common.logging import get_logger

from ecg_aggregator.domain.time import (
    DeviceClockSeconds,
    DeviceTimestampUs,
    GlobalTimeSeconds,
    HostTimeSeconds,
    OffsetSeconds,
    Seconds,
)
from ecg_aggregator.sync.types import DeviceSyncStats, SyncStats

logger = get_logger(__name__)

TIME_DISCONTINUITY_THRESHOLD_US = DeviceTimestampUs(10_000_000)  # 10 seconds


@dataclass
class TimeModel:
    """Time synchronization model for a device."""

    drift: float  # Clock drift multiplier
    offset: OffsetSeconds  # Clock offset in seconds
    confidence: float  # Model confidence (R² score)
    sample_count: int  # Number of samples used
    last_update: HostTimeSeconds  # Last update timestamp (host time)


@dataclass
class SyncedTimestamp:
    """A synchronized timestamp with confidence."""

    device_id: str
    device_timestamp: DeviceTimestampUs  # Original device timestamp (microseconds)
    global_time: GlobalTimeSeconds  # Synchronized global time (seconds since epoch)
    confidence: float  # Sync confidence (0-1)


class DeviceTimeModel:
    """Maintains time synchronization model for a single device."""

    def __init__(
        self,
        device_id: str,
        window_size: int = 100,
        min_samples: int = 5,
    ):
        """Initialize device time model.

        Args:
            device_id: Device identifier
            window_size: Size of sliding window (not used in offset mode)
            min_samples: Minimum samples needed to calculate offset
        """
        self.device_id = device_id
        self.window_size = window_size
        self.min_samples = min_samples

        # Timestamp pairs for offset calculation
        self._device_times: list[DeviceClockSeconds] = []
        self._host_times: list[HostTimeSeconds] = []

        # Simple offset model
        self._offset: OffsetSeconds | None = None
        self._sample_count: int = 0
        self._offset_version: int = 0  # Increments each time offset is recalculated

        # Dropout detection - track separately per stream to handle ECG+ACC interleaving
        self._last_device_time_by_stream: dict[str, DeviceTimestampUs] = {}
        self._dropout_count = 0

    def add_sample(
        self,
        device_timestamp: DeviceTimestampUs,
        host_receive_time: HostTimeSeconds,
        sensor_type: str = "unknown",
    ) -> None:
        """Add a timestamp pair to the model.

        Args:
            device_timestamp: Device timestamp in microseconds
            host_receive_time: Host receive time in seconds since epoch
            sensor_type: Sensor type ("ecg" or "acc") to track timestamps separately per sensor
        """
        # Convert from microseconds to seconds
        device_time_s = DeviceClockSeconds(device_timestamp / 1_000_000.0)
        logger.debug(
            f"[TIME_ALIGN] {self.device_id} add_sample: device_ts_us={device_timestamp:.0f}, device_ts_s={device_time_s:.2f}, host_time={host_receive_time:.2f}, sensor={sensor_type}"
        )

        # Detect potential dropout/reconnection - check per sensor to handle ECG+ACC interleaving
        if sensor_type in self._last_device_time_by_stream:
            last_time = self._last_device_time_by_stream[sensor_type]
            time_jump = device_timestamp - last_time
            # Treat large forward jumps as a device reconnect and reset the learned model.
            if time_jump < 0 or time_jump > TIME_DISCONTINUITY_THRESHOLD_US:
                logger.warning(
                    f"Device {self.device_id} [{sensor_type}] time discontinuity: {time_jump / 1_000_000:.2f}s "
                    f"(last={last_time}, current={device_timestamp})"
                )
                self._dropout_count += 1
                # Clear history on reconnection
                self._device_times.clear()
                self._host_times.clear()
                self._offset = None
                self._sample_count = 0

        self._last_device_time_by_stream[sensor_type] = device_timestamp

        # Add to list if offset not yet calculated
        if self._offset is None:
            self._device_times.append(device_time_s)
            self._host_times.append(host_receive_time)

            # Calculate offset when we have enough samples
            if len(self._device_times) >= self.min_samples:
                self._calculate_offset()

        self._sample_count += 1

    def _calculate_offset(self) -> None:
        """Calculate simple time offset between device and host clocks.

        Uses median of differences to be robust against outliers.
        Assumes clocks run at the same speed (drift ≈ 1.0).
        """
        try:
            # Calculate offset for each sample pair
            offsets = [
                OffsetSeconds(host_time - device_time)
                for device_time, host_time in zip(self._device_times, self._host_times, strict=True)
            ]

            # Use median for robustness
            self._offset = OffsetSeconds(float(np.median(offsets)))

            # Increment version counter (signals offset was recalculated)
            self._offset_version += 1

            logger.info(
                f"[TIME_ALIGN] Device {self.device_id} time offset calculated: {self._offset:.3f}s "
                f"(from {len(offsets)} samples, version {self._offset_version})"
            )
            logger.debug(
                f"[TIME_ALIGN] Offset details: device_times_s={self._device_times[:3]}, host_times={self._host_times[:3]}, offsets={offsets[:3]}"
            )

            # Clear the lists to free memory
            self._device_times.clear()
            self._host_times.clear()

        except Exception as e:
            logger.error(f"Error calculating offset for {self.device_id}: {e}")
            self._offset = None

    def sync_timestamp(self, device_timestamp: DeviceTimestampUs) -> SyncedTimestamp | None:
        """Convert device timestamp to global time.

        Args:
            device_timestamp: Device timestamp in microseconds

        Returns:
            SyncedTimestamp if offset available, None otherwise
        """
        if self._offset is None:
            return None

        # Convert device timestamp from microseconds to seconds
        device_time_s = DeviceClockSeconds(device_timestamp / 1_000_000.0)

        # Apply offset: global_time = device_time + offset
        global_time = GlobalTimeSeconds(device_time_s + self._offset)

        logger.debug(
            f"[TIME_ALIGN] {self.device_id} sync: device_ts_us={device_timestamp:.0f}, device_ts_s={device_time_s:.2f}, offset={self._offset:.2f}, global_time={global_time:.2f}"
        )

        return SyncedTimestamp(
            device_id=self.device_id,
            device_timestamp=device_timestamp,
            global_time=global_time,
            confidence=1.0,  # Simple offset is always reliable
        )

    @property
    def model(self) -> TimeModel | None:
        """Get the current time model."""
        if self._offset is None:
            return None

        return TimeModel(
            drift=1.0,  # Assuming no drift
            offset=self._offset,
            confidence=1.0,
            sample_count=self._sample_count,
            last_update=HostTimeSeconds(time.time()),
        )

    @property
    def is_ready(self) -> bool:
        """Check if offset is ready for synchronization."""
        return self._offset is not None

    @property
    def offset(self) -> OffsetSeconds | None:
        """Get the calculated offset."""
        return self._offset

    @property
    def offset_version(self) -> int:
        """Get the offset version (increments on each recalculation)."""
        return self._offset_version

    @property
    def dropout_count(self) -> int:
        """Get number of detected dropouts."""
        return self._dropout_count


class TimeAlignmentService:
    """Manages time synchronization for multiple devices."""

    def __init__(
        self,
        window_size: int = 100,
        min_samples: int = 5,
        confidence_threshold: float = 0.9,
    ):
        """Initialize time alignment service.

        Args:
            window_size: Size of window (not used in offset mode)
            min_samples: Minimum samples needed to calculate offset
            confidence_threshold: Minimum confidence for reliable sync (not used in offset mode)
        """
        self.window_size = window_size
        self.min_samples = min_samples
        self.confidence_threshold = confidence_threshold

        self._device_models: dict[str, DeviceTimeModel] = {}

    def register_device(self, device_id: str) -> None:
        """Register a device for time synchronization.

        Args:
            device_id: Device identifier
        """
        if device_id not in self._device_models:
            self._device_models[device_id] = DeviceTimeModel(
                device_id=device_id,
                window_size=self.window_size,
                min_samples=self.min_samples,
            )
            logger.info(f"Registered device {device_id} for time sync")

    def add_timestamp_pair(
        self,
        device_id: str,
        device_timestamp: DeviceTimestampUs,
        host_receive_time: HostTimeSeconds,
        sensor_type: str = "unknown",
    ) -> None:
        """Add a timestamp pair for synchronization.

        Args:
            device_id: Device identifier
            device_timestamp: Device timestamp in microseconds
            host_receive_time: Host receive time in seconds since epoch
            sensor_type: Sensor type ("ecg" or "acc")
        """
        # Auto-register device if not already registered
        if device_id not in self._device_models:
            self.register_device(device_id)

        self._device_models[device_id].add_sample(device_timestamp, host_receive_time, sensor_type)

    def sync_timestamp(
        self, device_id: str, device_timestamp: DeviceTimestampUs
    ) -> SyncedTimestamp | None:
        """Convert device timestamp to global time.

        Args:
            device_id: Device identifier
            device_timestamp: Device timestamp in microseconds

        Returns:
            SyncedTimestamp if sync available, None otherwise
        """
        model = self._device_models.get(device_id)
        if model is None:
            return None

        return model.sync_timestamp(device_timestamp)

    def get_device_model(self, device_id: str) -> TimeModel | None:
        """Get time model for a device.

        Args:
            device_id: Device identifier

        Returns:
            TimeModel if available, None otherwise
        """
        model = self._device_models.get(device_id)
        return model.model if model else None

    def get_offset_version(self, device_id: str) -> int | None:
        """Get the current offset version for a device, if available."""
        model = self._device_models.get(device_id)
        return model.offset_version if model else None

    def get_offset_versions(self, device_ids: Iterable[str]) -> dict[str, int]:
        """Get offset versions for the provided devices."""
        versions: dict[str, int] = {}
        for device_id in device_ids:
            offset_version = self.get_offset_version(device_id)
            if offset_version is not None:
                versions[device_id] = offset_version
        return versions

    def is_device_ready(self, device_id: str) -> bool:
        """Check if device is ready for synchronization.

        Args:
            device_id: Device identifier

        Returns:
            True if device has reliable time sync
        """
        model = self._device_models.get(device_id)
        return model.is_ready if model else False

    def get_all_models(self) -> dict[str, TimeModel | None]:
        """Get time models for all devices.

        Returns:
            Dictionary mapping device IDs to their TimeModel
        """
        return {device_id: model.model for device_id, model in self._device_models.items()}

    def get_sync_stats(self) -> SyncStats:
        """Get synchronization statistics for all devices.

        Returns:
            Dictionary with sync statistics
        """
        devices_dict: dict[str, DeviceSyncStats] = {}
        stats: SyncStats = {
            "total_devices": len(self._device_models),
            "ready_devices": sum(1 for m in self._device_models.values() if m.is_ready),
            "devices": devices_dict,
        }

        for device_id, model in self._device_models.items():
            device_stats: DeviceSyncStats = {
                "ready": model.is_ready,
                "dropouts": model.dropout_count,
            }

            if model.model:
                drift_ppm = (model.model.drift - 1.0) * 1_000_000
                device_stats.update(
                    {
                        "drift": Seconds(model.model.drift),
                        "drift_ppm": drift_ppm,
                        "offset": model.model.offset,
                        "confidence": model.model.confidence,
                        "sample_count": model.model.sample_count,
                        "age_seconds": Seconds(time.time() - model.model.last_update),
                    }
                )

            devices_dict[device_id] = device_stats

        return stats

    def reset_device(self, device_id: str) -> bool:
        """Reset time synchronization for a device.

        Args:
            device_id: Device identifier

        Returns:
            True if device was reset, False if not found
        """
        if device_id in self._device_models:
            del self._device_models[device_id]
            self.register_device(device_id)
            logger.info(f"Reset time sync for device {device_id}")
            return True
        return False
