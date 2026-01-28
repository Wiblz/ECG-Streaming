"""Real-time accelerometer spike detection for calibration."""

import time
from collections import deque
from dataclasses import dataclass

from ecg_common.logging import get_logger

logger = get_logger(__name__)


@dataclass
class AccSample:
    """Accelerometer sample."""

    device_id: str
    global_time: float  # Seconds since epoch
    device_timestamp: float  # Device microseconds
    x: float
    y: float
    z: float
    magnitude: float


@dataclass
class TapEvent:
    """Detected tap/spike event."""

    device_id: str
    tap_timestamp: float  # Global time (seconds)
    device_timestamp: float  # Device microseconds
    magnitude: float  # Peak magnitude in G
    confidence: float  # Detection confidence (0-1)
    detected_at: float  # Time when detection occurred


class SpikeDetector:
    """Real-time accelerometer spike detection.

    Detects ACC spikes from tap events or vibration patterns.
    Designed to work with both manual taps (visual calibration)
    and future vibration pattern matching.
    """

    def __init__(
        self,
        threshold: float = 2.0,  # G
        min_interval: float = 0.3,  # seconds between taps
        window_size: int = 50,  # samples for context
        smoothing_window: int = 3,  # samples for magnitude smoothing
    ):
        """Initialize spike detector.

        Args:
            threshold: Minimum magnitude (G) to consider as tap
            min_interval: Minimum time between detected taps (seconds)
            window_size: Number of recent samples to keep per device
            smoothing_window: Number of samples for moving average smoothing
        """
        self.threshold = threshold
        self.min_interval = min_interval
        self.window_size = window_size
        self.smoothing_window = smoothing_window

        # Per-device state for real-time processing
        self.device_buffers: dict[str, deque[AccSample]] = {}
        self.last_tap_time: dict[str, float] = {}
        self.total_taps_detected = 0

    def process_sample(self, sample: AccSample) -> TapEvent | None:
        """Process single ACC sample in real-time.

        Args:
            sample: Accelerometer sample with magnitude already computed

        Returns:
            TapEvent if tap detected, None otherwise
        """
        device_id = sample.device_id

        # Initialize device buffer if needed
        if device_id not in self.device_buffers:
            self.device_buffers[device_id] = deque(maxlen=self.window_size)
            self.last_tap_time[device_id] = 0.0

        buffer = self.device_buffers[device_id]
        buffer.append(sample)

        # Need minimum context for peak detection
        min_context = max(self.smoothing_window + 1, 3)
        if len(buffer) < min_context:
            return None

        # Apply simple moving average smoothing to reduce noise
        current_mag = self._get_smoothed_magnitude(buffer, -1)

        # Check if current sample is above threshold
        if current_mag < self.threshold:
            return None

        # Verify it's a local maximum (peak detection)
        # Compare with previous samples to ensure we're at the peak
        prev_mag = self._get_smoothed_magnitude(buffer, -2)
        prev2_mag = (
            self._get_smoothed_magnitude(buffer, -3) if len(buffer) >= min_context + 1 else 0
        )

        # Current sample must be higher than previous ones (rising edge of peak)
        # and previous must be higher than one before (confirming peak shape)
        is_peak = current_mag > prev_mag and prev_mag > prev2_mag

        if not is_peak:
            return None

        # Check minimum interval since last tap for this device
        last_tap = self.last_tap_time[device_id]
        time_since_last = sample.global_time - last_tap

        if time_since_last < self.min_interval:
            return None

        # Valid tap detected!
        self.last_tap_time[device_id] = sample.global_time
        self.total_taps_detected += 1

        # Calculate confidence based on magnitude
        # Higher magnitude = higher confidence (cap at 1.0)
        # Scale: 2G = 0.4, 3G = 0.6, 4G = 0.8, 5G+ = 1.0
        confidence = min(1.0, (current_mag - self.threshold) / 3.0 + 0.4)

        tap_event = TapEvent(
            device_id=device_id,
            tap_timestamp=sample.global_time,
            device_timestamp=sample.device_timestamp,
            magnitude=current_mag,
            confidence=confidence,
            detected_at=time.time(),
        )

        logger.debug(
            f"Tap detected: device={device_id}, mag={current_mag:.2f}G, "
            f"confidence={confidence:.2f}, time_since_last={time_since_last:.2f}s"
        )

        return tap_event

    def _get_smoothed_magnitude(self, buffer: deque[AccSample], index: int) -> float:
        """Get smoothed magnitude at buffer index using moving average.

        Args:
            buffer: Sample buffer
            index: Index in buffer (negative for from-end indexing)

        Returns:
            Smoothed magnitude value
        """
        if len(buffer) == 0:
            return 0.0

        # Convert negative index to positive
        if index < 0:
            index = len(buffer) + index

        if index < 0 or index >= len(buffer):
            return 0.0

        # Calculate moving average window
        half_window = self.smoothing_window // 2
        start_idx = max(0, index - half_window)
        end_idx = min(len(buffer), index + half_window + 1)

        # Get magnitudes in window
        magnitudes = [buffer[i].magnitude for i in range(start_idx, end_idx)]

        # Return average
        return sum(magnitudes) / len(magnitudes) if magnitudes else 0.0

    def reset_device(self, device_id: str) -> None:
        """Reset detector state for a device.

        Args:
            device_id: Device identifier
        """
        if device_id in self.device_buffers:
            del self.device_buffers[device_id]
        if device_id in self.last_tap_time:
            del self.last_tap_time[device_id]

        logger.info(f"Reset spike detector for device {device_id}")

    def get_stats(self) -> dict[str, object]:
        """Get detector statistics.

        Returns:
            Dictionary with detector stats
        """
        device_stats = {}
        for device_id, buffer in self.device_buffers.items():
            device_stats[device_id] = {
                "buffer_size": len(buffer),
                "last_tap": self.last_tap_time.get(device_id, 0),
            }

        return {
            "total_taps_detected": self.total_taps_detected,
            "active_devices": len(self.device_buffers),
            "devices": device_stats,
        }
