"""Circular buffer for storing synchronized ECG and accelerometer data."""

import math
import time
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import asdict, dataclass
from threading import RLock
from typing import Any

from ecg_common.models import (
    BufferedAccelerometerSample,
    BufferedECGSample,
    BufferedSample,
)

RATE_WINDOW_SECONDS = 3.0
RATE_BUCKET_SECONDS = 1.0


@dataclass
class _RateBuckets:
    buckets: deque[tuple[int, int]]
    total: int


class DataBuffer[T: BufferedSample](ABC):
    """Generic circular buffer for storing synchronized sensor data.

    This base class provides all common buffer operations. Subclasses
    only need to implement the add_sample() method specific to their
    data type.

    Type-safe through generics - the buffer type T must inherit from
    BufferedSample (guaranteeing device_id, global_time, and confidence).
    """

    def __init__(self, duration_seconds: int = 30, max_samples: int = 100000):
        """Initialize the data buffer.

        Args:
            duration_seconds: Duration of data to keep in seconds
            max_samples: Maximum number of samples to store (safety limit)
        """
        self.duration_seconds = duration_seconds
        self.max_samples = max_samples

        self._buffer: deque[T] = deque(maxlen=max_samples)
        self._lock = RLock()

        # Statistics
        self._total_samples = 0
        self._rate_bucket_count = int(RATE_WINDOW_SECONDS / RATE_BUCKET_SECONDS)
        self._rate_buckets: dict[str, _RateBuckets] = {}
        self._rate_total = 0

    @abstractmethod
    def add_sample(self, *args: Any, **kwargs: Any) -> None:
        """Add a synchronized sample to the buffer.

        This method must be implemented by subclasses to handle
        their specific sample type and parameters.
        """
        pass

    def _advance_rate_buckets(self, rate: _RateBuckets, current_bucket: int) -> None:
        if not rate.buckets:
            rate.buckets.append((current_bucket, 0))
            return

        last_bucket = rate.buckets[-1][0]
        if current_bucket <= last_bucket:
            return

        gap = current_bucket - last_bucket
        if gap >= self._rate_bucket_count:
            self._rate_total -= rate.total
            rate.total = 0
            rate.buckets.clear()
            rate.buckets.append((current_bucket, 0))
            return

        for bucket in range(last_bucket + 1, current_bucket + 1):
            rate.buckets.append((bucket, 0))

        while rate.buckets and current_bucket - rate.buckets[0][0] >= self._rate_bucket_count:
            _, old_count = rate.buckets.popleft()
            rate.total -= old_count
            self._rate_total -= old_count

    def _record_rate_sample(self, device_id: str, timestamp_s: float) -> None:
        current_bucket = int(timestamp_s // RATE_BUCKET_SECONDS)
        rate = self._rate_buckets.get(device_id)
        if rate is None:
            rate = _RateBuckets(buckets=deque(), total=0)
            self._rate_buckets[device_id] = rate

        self._advance_rate_buckets(rate, current_bucket)

        if not rate.buckets or rate.buckets[-1][0] != current_bucket:
            rate.buckets.append((current_bucket, 0))

        bucket_start, bucket_count = rate.buckets[-1]
        rate.buckets[-1] = (bucket_start, bucket_count + 1)
        rate.total += 1
        self._rate_total += 1

    def _prune_rate_buckets(self, now_s: float) -> None:
        current_bucket = int(now_s // RATE_BUCKET_SECONDS)
        to_delete = []
        for device_id, rate in self._rate_buckets.items():
            self._advance_rate_buckets(rate, current_bucket)
            if rate.total == 0:
                to_delete.append(device_id)
        for device_id in to_delete:
            del self._rate_buckets[device_id]

    def _cleanup_old_samples(self) -> None:
        """Remove samples older than the buffer duration."""
        if not self._buffer:
            return

        from ecg_common.logging import get_logger

        logger = get_logger(__name__)

        cutoff_time = time.time() - self.duration_seconds
        removed_count = 0

        # Remove old samples from the left
        while self._buffer and self._buffer[0].global_time < cutoff_time:
            old_sample = self._buffer.popleft()
            removed_count += 1
            if removed_count <= 3:  # Log first few removals
                logger.debug(
                    f"[BUFFER] Removed old sample: global_time={old_sample.global_time:.2f}, cutoff={cutoff_time:.2f}, age={time.time() - old_sample.global_time:.2f}s"
                )

        if removed_count > 0:
            logger.debug(
                f"[BUFFER] Cleanup removed {removed_count} samples, {len(self._buffer)} remaining"
            )

    def get_recent_samples(
        self,
        since: float | None = None,
        device_id: str | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        """Get recent samples from the buffer.

        Args:
            since: Only return samples after this timestamp (optional)
            device_id: Filter by device ID (optional)
            limit: Maximum number of samples to return (optional)

        Returns:
            List of sample dictionaries
        """
        with self._lock:
            samples = list(self._buffer)

        # Filter by timestamp
        if since is not None:
            samples = [s for s in samples if s.global_time > since]

        # Filter by device
        if device_id is not None:
            samples = [s for s in samples if s.device_id == device_id]

        # Apply limit
        if limit is not None:
            samples = samples[-limit:]

        # Convert to dictionaries
        return [asdict(sample) for sample in samples]

    def get_latest_by_device(self) -> dict[str, dict]:
        """Get the latest sample for each device.

        Returns:
            Dictionary mapping device IDs to their latest sample
        """
        with self._lock:
            samples = list(self._buffer)

        latest = {}
        for sample in reversed(samples):
            if sample.device_id not in latest:
                latest[sample.device_id] = asdict(sample)

        return latest

    def get_time_range(self) -> tuple[float | None, float | None]:
        """Get the time range of data in the buffer.

        Returns:
            Tuple of (oldest_time, newest_time) or (None, None) if empty
        """
        with self._lock:
            if not self._buffer:
                return None, None
            return self._buffer[0].global_time, self._buffer[-1].global_time

    def get_sample_count(self, device_id: str | None = None) -> int:
        """Get the number of samples in the buffer.

        Args:
            device_id: Optional device ID to count samples for

        Returns:
            Number of samples
        """
        with self._lock:
            if device_id is None:
                return len(self._buffer)
            return sum(1 for s in self._buffer if s.device_id == device_id)

    def get_device_list(self) -> list[str]:
        """Get list of device IDs currently in the buffer.

        Returns:
            List of unique device IDs
        """
        with self._lock:
            return list({s.device_id for s in self._buffer})

    def get_stats(self) -> dict:
        """Get buffer statistics.

        Returns:
            Dictionary with buffer statistics
        """
        with self._lock:
            now = time.time()
            self._prune_rate_buckets(now)
            if self._buffer:
                oldest = self._buffer[0].global_time
                newest = self._buffer[-1].global_time
                duration = newest - oldest
            else:
                oldest = None
                newest = None
                duration = 0

            device_counts: dict[str, int] = {}
            for sample in self._buffer:
                device_counts[sample.device_id] = device_counts.get(sample.device_id, 0) + 1

            device_rates: dict[str, float] = {}
            for device_id in device_counts:
                rate = self._rate_buckets.get(device_id)
                device_rates[device_id] = rate.total / RATE_WINDOW_SECONDS if rate else 0.0
            total_rate = self._rate_total / RATE_WINDOW_SECONDS

            return {
                "total_samples": len(self._buffer),
                "duration_seconds": duration,
                "device_count": len(device_counts),
                "samples_per_device": device_counts,
                "samples_per_second": total_rate,
                "samples_per_second_per_device": device_rates,
                "oldest_timestamp": oldest,
                "newest_timestamp": newest,
                "total_processed": self._total_samples,
                "buffer_utilization": len(self._buffer) / self.max_samples,
            }

    def clear(self) -> None:
        """Clear all samples from the buffer."""
        with self._lock:
            self._buffer.clear()
            self._total_samples = 0
            self._rate_buckets.clear()
            self._rate_total = 0

    def clear_device(self, device_id: str) -> int:
        """Clear samples for a specific device.

        Args:
            device_id: Device identifier

        Returns:
            Number of samples removed
        """
        with self._lock:
            original_len = len(self._buffer)
            self._buffer = deque(
                (s for s in self._buffer if s.device_id != device_id),
                maxlen=self.max_samples,
            )
            removed = original_len - len(self._buffer)
            rate = self._rate_buckets.pop(device_id, None)
            if rate:
                self._rate_total -= rate.total
            return removed


class ECGDataBuffer(DataBuffer[BufferedECGSample]):
    """Circular buffer for storing synchronized ECG data.

    Maintains a time-based sliding window of ECG samples
    across all devices.
    """

    def add_sample(
        self,
        device_id: str,
        global_time: float,
        raw_value: int,
        confidence: float,
        wall_clock_us: int,
        polar_clock_us: int,
        receiver_clock_us: int,
        time_verified: bool = False,
    ) -> None:
        """Add a synchronized ECG sample to the buffer.

        Args:
            device_id: Device identifier
            global_time: Synchronized global timestamp
            raw_value: Raw ECG value
            confidence: Synchronization confidence
            wall_clock_us: Wall clock (epoch time) when collector received frame (microseconds)
            polar_clock_us: Polar device timestamp (microseconds since Polar boot)
            receiver_clock_us: Receiver device clock (microseconds since ESP32/collector boot)
            time_verified: True if polar timestamp came directly from PMD frame (not interpolated)
        """
        import time as time_module

        from ecg_common.logging import get_logger

        logger = get_logger(__name__)

        # Create unique sample ID from device_id and polar_clock_us
        sample_id = f"{device_id}:{polar_clock_us}"

        sample = BufferedECGSample(
            id=sample_id,
            device_id=device_id,
            global_time=global_time,
            raw_value=raw_value,
            confidence=confidence,
            wall_clock_us=wall_clock_us,
            receiver_clock_us=receiver_clock_us,
            polar_clock_us=polar_clock_us,
            time_verified=time_verified,
        )

        with self._lock:
            buffer_size_before = len(self._buffer)
            self._buffer.append(sample)
            self._total_samples += 1
            self._record_rate_sample(device_id, wall_clock_us / 1_000_000.0)

            logger.debug(
                f"[BUFFER] Added sample: device={device_id}, global_time={global_time:.2f}, now={time_module.time():.2f}, diff={time_module.time() - global_time:.2f}s, buffer_size={buffer_size_before + 1}"
            )

            # Clean old samples
            self._cleanup_old_samples()

            buffer_size_after = len(self._buffer)
            if buffer_size_after < buffer_size_before + 1:
                logger.debug(
                    f"[BUFFER] Sample was cleaned immediately! Buffer size: {buffer_size_before + 1} -> {buffer_size_after}"
                )


class AccelerometerDataBuffer(DataBuffer[BufferedAccelerometerSample]):
    """Circular buffer for storing synchronized accelerometer data.

    Maintains a time-based sliding window of accelerometer samples
    across all devices.
    """

    def add_sample(
        self,
        device_id: str,
        global_time: float,
        x: float,
        y: float,
        z: float,
        confidence: float,
        wall_clock_us: int,
        polar_clock_us: int,
        receiver_clock_us: int,
        time_verified: bool = False,
    ) -> None:
        """Add a synchronized accelerometer sample to the buffer.

        Calculates the motion magnitude (total acceleration) from x, y, z components.

        Args:
            device_id: Device identifier
            global_time: Synchronized global timestamp
            x: X-axis acceleration (g)
            y: Y-axis acceleration (g)
            z: Z-axis acceleration (g)
            confidence: Synchronization confidence
            wall_clock_us: Wall clock (epoch time) when collector received frame (microseconds)
            polar_clock_us: Polar device timestamp (microseconds since Polar boot)
            receiver_clock_us: Receiver device clock (microseconds since ESP32/collector boot)
            time_verified: True if polar timestamp came directly from PMD frame (not interpolated)
        """
        # Calculate motion magnitude (total acceleration vector length)
        magnitude = math.sqrt(x**2 + y**2 + z**2)

        # Create unique sample ID from device_id and polar_clock_us
        sample_id = f"{device_id}:{polar_clock_us}"

        sample = BufferedAccelerometerSample(
            id=sample_id,
            device_id=device_id,
            global_time=global_time,
            x=x,
            y=y,
            z=z,
            magnitude=magnitude,
            confidence=confidence,
            wall_clock_us=wall_clock_us,
            receiver_clock_us=receiver_clock_us,
            polar_clock_us=polar_clock_us,
            time_verified=time_verified,
        )

        with self._lock:
            self._buffer.append(sample)
            self._total_samples += 1
            self._record_rate_sample(device_id, wall_clock_us / 1_000_000.0)

            # Clean old samples
            self._cleanup_old_samples()
