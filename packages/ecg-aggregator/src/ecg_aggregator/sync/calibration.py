"""Calibration correlation and alignment computation."""

import time
from dataclasses import dataclass, field

import numpy as np
from ecg_common.logging import get_logger

from ecg_aggregator.sync.spike_detector import TapEvent

logger = get_logger(__name__)


@dataclass
class FlashEvent:
    """Flash or vibration event for calibration."""

    flash_id: int
    flash_timestamp: float  # Host time (seconds since epoch)
    event_type: str = "visual"  # "visual" or "vibration"
    pattern_id: str | None = None  # For future vibration patterns


@dataclass
class TapFlashPair:
    """Matched tap-flash pair for alignment computation."""

    device_id: str
    tap_event: TapEvent
    flash_event: FlashEvent
    reaction_time: float  # Time between flash and tap (seconds)
    confidence: float  # Match confidence (0-1)


@dataclass
class DeviceAlignment:
    """Computed time alignment for a device."""

    device_id: str
    time_offset: float  # Offset in seconds (flash_time - device_time)
    drift: float  # Clock drift multiplier
    confidence: float  # Overall confidence (0-1)
    tap_count: int  # Number of taps used
    mean_error: float | None = None  # Mean alignment error (seconds)
    std_error: float | None = None  # Standard deviation of error
    status: str = (
        "waiting_for_taps"  # Status: waiting_for_taps, calibrating, aligned, insufficient_data
    )
    last_updated: float = field(default_factory=time.time)
    offsets: list[float] = field(default_factory=list)  # History of computed offsets
    offset_version: int | None = None  # TimeAlignmentService offset version


class CalibrationCorrelator:
    """Matches detected taps to flash events."""

    def __init__(
        self,
        max_reaction_time: float = 0.5,  # Maximum human reaction time (seconds)
        min_reaction_time: float = 0.05,  # Minimum human reaction time (seconds)
    ):
        """Initialize correlator.

        Args:
            max_reaction_time: Maximum expected reaction time (seconds)
            min_reaction_time: Minimum expected reaction time (seconds)
        """
        self.max_reaction_time = max_reaction_time
        self.min_reaction_time = min_reaction_time

    def match_tap_to_flash(
        self, tap_event: TapEvent, flash_events: list[FlashEvent]
    ) -> TapFlashPair | None:
        """Match a tap event to the most likely flash event.

        Args:
            tap_event: Detected tap event
            flash_events: List of flash events (should be time-ordered)

        Returns:
            TapFlashPair if match found, None otherwise
        """
        if not flash_events:
            return None

        # Find flash events within valid reaction time window
        # Flash must have occurred BEFORE the tap
        candidates: list[tuple[FlashEvent, float, float]] = []

        for flash in flash_events:
            reaction_time = tap_event.tap_timestamp - flash.flash_timestamp

            # Check if reaction time is within valid range
            if self.min_reaction_time <= reaction_time <= self.max_reaction_time:
                # Calculate match confidence based on reaction time
                # Closer to typical reaction time (0.2s) = higher confidence
                typical_reaction = 0.2
                time_deviation = abs(reaction_time - typical_reaction)
                time_confidence = max(0.0, 1.0 - (time_deviation / self.max_reaction_time))

                # Combine with tap detection confidence
                combined_confidence = (tap_event.confidence + time_confidence) / 2.0

                candidates.append((flash, reaction_time, combined_confidence))

        if not candidates:
            logger.debug(
                f"No matching flash found for tap at {tap_event.tap_timestamp} "
                f"(device {tap_event.device_id})"
            )
            return None

        # Pick the candidate with highest confidence
        # (usually the closest flash within valid range)
        best_flash, reaction_time, confidence = max(candidates, key=lambda x: x[2])

        logger.debug(
            f"Matched tap (device={tap_event.device_id}, t={tap_event.tap_timestamp:.3f}) "
            f"to flash (id={best_flash.flash_id}, t={best_flash.flash_timestamp:.3f}), "
            f"reaction={reaction_time:.3f}s, confidence={confidence:.2f}"
        )

        return TapFlashPair(
            device_id=tap_event.device_id,
            tap_event=tap_event,
            flash_event=best_flash,
            reaction_time=reaction_time,
            confidence=confidence,
        )


class AlignmentComputer:
    """Incrementally computes time alignment from tap-flash pairs."""

    def __init__(
        self,
        min_pairs: int = 3,  # Minimum pairs needed for alignment
        max_error: float = 0.1,  # Maximum acceptable mean error (seconds)
        outlier_threshold: float = 0.15,  # Outlier rejection threshold (seconds)
    ):
        """Initialize alignment computer.

        Args:
            min_pairs: Minimum matched pairs needed for reliable alignment
            max_error: Maximum acceptable mean error (seconds)
            outlier_threshold: Threshold for outlier rejection (seconds from median)
        """
        self.min_pairs = min_pairs
        self.max_error = max_error
        self.outlier_threshold = outlier_threshold

    def update_alignment(
        self, existing: DeviceAlignment | None, new_pair: TapFlashPair
    ) -> DeviceAlignment:
        """Update alignment with new matched tap-flash pair.

        Args:
            existing: Existing alignment (None if first pair)
            new_pair: New matched tap-flash pair

        Returns:
            Updated device alignment
        """
        # Compute offset for this pair
        # offset = flash_timestamp - device_timestamp_seconds
        device_time_s = new_pair.tap_event.device_timestamp / 1_000_000.0
        new_offset = new_pair.flash_event.flash_timestamp - device_time_s

        if existing is None:
            # First pair - initialize alignment
            return DeviceAlignment(
                device_id=new_pair.device_id,
                time_offset=new_offset,
                drift=1.0,
                confidence=0.3,  # Low confidence with just 1 pair
                tap_count=1,
                offsets=[new_offset],
                status="waiting_for_taps",
                last_updated=time.time(),
            )

        # Add to existing offsets
        all_offsets = existing.offsets + [new_offset]
        tap_count = len(all_offsets)

        # Reject outliers using robust statistics
        filtered_offsets = self._reject_outliers(all_offsets)

        if len(filtered_offsets) < 2:
            # Not enough valid offsets after filtering
            logger.warning(
                f"Too many outliers for device {new_pair.device_id} "
                f"({len(all_offsets) - len(filtered_offsets)}/{len(all_offsets)})"
            )
            filtered_offsets = all_offsets  # Use all if filtering is too aggressive

        # Compute robust offset (median)
        median_offset = float(np.median(filtered_offsets))

        # Compute error statistics
        errors = [abs(o - median_offset) for o in filtered_offsets]
        mean_error = float(np.mean(errors))
        std_error = float(np.std(errors)) if len(errors) > 1 else 0.0

        # Compute drift if we have enough pairs (linear regression)
        drift = 1.0  # Default: assume no drift
        # TODO: Implement drift computation with linear regression when tap_count > 10

        # Determine status and confidence
        status, confidence = self._compute_status_and_confidence(
            tap_count=tap_count,
            mean_error=mean_error,
            std_error=std_error,
            filtered_count=len(filtered_offsets),
            total_count=len(all_offsets),
        )

        return DeviceAlignment(
            device_id=new_pair.device_id,
            time_offset=median_offset,
            drift=drift,
            confidence=confidence,
            tap_count=tap_count,
            mean_error=mean_error,
            std_error=std_error,
            offsets=all_offsets,  # Keep all offsets for history
            status=status,
            last_updated=time.time(),
        )

    def _reject_outliers(self, offsets: list[float]) -> list[float]:
        """Reject outliers using median absolute deviation (MAD).

        Args:
            offsets: List of offset values

        Returns:
            Filtered list without outliers
        """
        if len(offsets) < 3:
            return offsets  # Not enough data for outlier detection

        median = float(np.median(offsets))

        # Compute absolute deviations from median
        deviations = [abs(o - median) for o in offsets]

        # Filter offsets where deviation exceeds threshold
        filtered = [
            o for o, dev in zip(offsets, deviations, strict=True) if dev <= self.outlier_threshold
        ]

        return filtered if filtered else offsets  # Return original if all rejected

    def _compute_status_and_confidence(
        self,
        tap_count: int,
        mean_error: float,
        std_error: float,
        filtered_count: int,
        total_count: int,
    ) -> tuple[str, float]:
        """Compute alignment status and confidence.

        Args:
            tap_count: Total number of taps
            mean_error: Mean alignment error
            std_error: Standard deviation of error
            filtered_count: Number of offsets after outlier rejection
            total_count: Total number of offsets

        Returns:
            Tuple of (status, confidence)
        """
        # Check if we have minimum taps
        if tap_count < self.min_pairs:
            status = "waiting_for_taps"
            confidence = tap_count / self.min_pairs * 0.5
            return status, confidence

        # Check if mean error is acceptable
        if mean_error > self.max_error:
            status = "insufficient_data"
            confidence = max(0.2, 1.0 - (mean_error / self.max_error))
            return status, confidence

        # Check outlier ratio
        outlier_ratio = 1.0 - (filtered_count / total_count)
        if outlier_ratio > 0.3:  # More than 30% outliers
            status = "insufficient_data"
            confidence = 0.4
            return status, confidence

        # Good alignment - compute confidence
        # Factors: tap count, error consistency, outlier ratio
        tap_factor = min(1.0, tap_count / 10)  # More taps = higher confidence (cap at 10)
        error_factor = max(0.0, 1.0 - (mean_error / self.max_error))
        consistency_factor = max(0.0, 1.0 - (std_error / self.max_error))
        outlier_factor = 1.0 - outlier_ratio

        confidence = (tap_factor + error_factor + consistency_factor + outlier_factor) / 4.0

        # Determine status based on confidence
        status = "aligned" if confidence >= 0.8 else "calibrating"

        return status, confidence
