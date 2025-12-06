"""Time alignment engine for synchronizing device timestamps."""

import time
from collections import deque
from dataclasses import dataclass

import numpy as np
from scipy import stats

from src.common.logging import get_logger

logger = get_logger(__name__)


@dataclass
class TimeModel:
    """Time synchronization model for a device."""

    drift: float  # Clock drift multiplier
    offset: float  # Clock offset in seconds
    confidence: float  # Model confidence (R² score)
    sample_count: int  # Number of samples used
    last_update: float  # Last update timestamp (host time)


@dataclass
class SyncedTimestamp:
    """A synchronized timestamp with confidence."""

    device_id: str
    device_timestamp: float  # Original device timestamp (microseconds)
    global_time: float  # Synchronized global time (seconds since epoch)
    confidence: float  # Sync confidence (0-1)


class DeviceTimeModel:
    """Maintains time synchronization model for a single device."""

    def __init__(
        self,
        device_id: str,
        window_size: int = 100,
        min_samples: int = 20,
    ):
        """Initialize device time model.

        Args:
            device_id: Device identifier
            window_size: Size of sliding window for regression
            min_samples: Minimum samples needed for valid model
        """
        self.device_id = device_id
        self.window_size = window_size
        self.min_samples = min_samples

        # Sliding window of timestamp pairs
        self._device_times: deque = deque(maxlen=window_size)
        self._host_times: deque = deque(maxlen=window_size)

        # Current model
        self._model: TimeModel | None = None

        # Dropout detection
        self._last_device_time: float | None = None
        self._dropout_count = 0

        # Reference point (first sample)
        self._device_t0: float | None = None
        self._host_t0: float | None = None

    def add_sample(self, device_timestamp: float, host_receive_time: float) -> None:
        """Add a timestamp pair to the model.

        Args:
            device_timestamp: Device timestamp in microseconds
            host_receive_time: Host receive time in seconds since epoch
        """
        # Detect potential dropout/reconnection
        if self._last_device_time is not None:
            time_jump = device_timestamp - self._last_device_time
            # If time jumped backwards or more than 10 seconds, likely a reconnection
            if time_jump < 0 or time_jump > 10_000_000:  # 10 seconds in microseconds
                logger.warning(
                    f"Device {self.device_id} time discontinuity: {time_jump / 1_000_000:.2f}s"
                )
                self._dropout_count += 1
                # Clear history on reconnection
                self._device_times.clear()
                self._host_times.clear()
                self._model = None

        self._last_device_time = device_timestamp

        # Add to windows (convert device time to seconds)
        self._device_times.append(device_timestamp / 1_000_000.0)
        self._host_times.append(host_receive_time)

        # Update model if we have enough samples
        if len(self._device_times) >= self.min_samples:
            self._update_model()

    def _update_model(self) -> None:
        """Update the time alignment model using linear regression.

        Since device timestamps are relative (microseconds since boot), we need to:
        1. Use the first sample as reference point (t0)
        2. Calculate deltas from t0 for both device and host times
        3. Regress to find: delta_host = drift * delta_device
        4. Use the offset to map device time to host time
        """
        try:
            device_times = np.array(self._device_times)
            host_times = np.array(self._host_times)

            # Use first sample as reference point
            device_t0 = device_times[0]
            host_t0 = host_times[0]

            # Calculate deltas from reference point
            device_deltas = device_times - device_t0
            host_deltas = host_times - host_t0

            # Perform linear regression on deltas: delta_host = drift * delta_device
            # This gives us the clock drift ratio
            # Force regression through origin by using deltas
            slope, intercept, r_value, _, _ = stats.linregress(device_deltas, host_deltas)

            # Calculate confidence from R²
            r_squared = r_value**2
            confidence = max(0.0, min(1.0, r_squared))

            # The slope is the drift ratio
            drift = slope
            # Map device time to host time: host_time = drift * device_time + offset
            # Using first sample as anchor: host_t0 = drift * device_t0 + offset
            # So: offset = host_t0 - drift * device_t0
            offset = host_t0 - (drift * device_t0)

            # Check for unrealistic drift (should be close to 1.0)
            drift_ppm = abs(drift - 1.0) * 1_000_000
            if drift_ppm > 1000:  # More than 1000 ppm (0.1%) is suspicious
                logger.warning(f"Device {self.device_id} has high clock drift: {drift_ppm:.1f} ppm")

            self._model = TimeModel(
                drift=drift,
                offset=offset,
                confidence=confidence,
                sample_count=len(device_times),
                last_update=time.time(),
            )

        except Exception as e:
            logger.error(f"Error updating time model for {self.device_id}: {e}")
            self._model = None

    def sync_timestamp(self, device_timestamp: float) -> SyncedTimestamp | None:
        """Convert device timestamp to global time.

        Args:
            device_timestamp: Device timestamp in microseconds

        Returns:
            SyncedTimestamp if model available, None otherwise
        """
        if self._model is None:
            return None

        # Convert device timestamp to seconds
        device_time_s = device_timestamp / 1_000_000.0

        # Apply model: global_time = drift * device_time + offset
        global_time = self._model.drift * device_time_s + self._model.offset

        return SyncedTimestamp(
            device_id=self.device_id,
            device_timestamp=device_timestamp,
            global_time=global_time,
            confidence=self._model.confidence,
        )

    @property
    def model(self) -> TimeModel | None:
        """Get the current time model."""
        return self._model

    @property
    def is_ready(self) -> bool:
        """Check if model is ready for synchronization."""
        return self._model is not None and self._model.confidence > 0.5

    @property
    def dropout_count(self) -> int:
        """Get number of detected dropouts."""
        return self._dropout_count


class TimeAlignmentService:
    """Manages time synchronization for multiple devices."""

    def __init__(
        self,
        window_size: int = 100,
        min_samples: int = 20,
        confidence_threshold: float = 0.9,
    ):
        """Initialize time alignment service.

        Args:
            window_size: Size of regression window per device
            min_samples: Minimum samples needed for valid model
            confidence_threshold: Minimum confidence for reliable sync
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
        self, device_id: str, device_timestamp: float, host_receive_time: float
    ) -> None:
        """Add a timestamp pair for synchronization.

        Args:
            device_id: Device identifier
            device_timestamp: Device timestamp in microseconds
            host_receive_time: Host receive time in seconds since epoch
        """
        # Auto-register device if not already registered
        if device_id not in self._device_models:
            self.register_device(device_id)

        self._device_models[device_id].add_sample(device_timestamp, host_receive_time)

    def sync_timestamp(self, device_id: str, device_timestamp: float) -> SyncedTimestamp | None:
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

    def get_sync_stats(self) -> dict[str, object]:
        """Get synchronization statistics for all devices.

        Returns:
            Dictionary with sync statistics
        """
        stats: dict[str, object] = {
            "total_devices": len(self._device_models),
            "ready_devices": sum(1 for m in self._device_models.values() if m.is_ready),
            "devices": {},
        }

        for device_id, model in self._device_models.items():
            device_stats: dict[str, object] = {
                "ready": model.is_ready,
                "dropouts": model.dropout_count,
            }

            if model.model:
                drift_ppm = (model.model.drift - 1.0) * 1_000_000
                device_stats.update(
                    {
                        "drift": model.model.drift,
                        "drift_ppm": drift_ppm,
                        "offset": model.model.offset,
                        "confidence": model.model.confidence,
                        "sample_count": model.model.sample_count,
                        "age_seconds": time.time() - model.model.last_update,
                    }
                )

            stats["devices"][device_id] = device_stats

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
