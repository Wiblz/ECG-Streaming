"""Calibration session management and orchestration."""

import time
from typing import TYPE_CHECKING

from ecg_common.logging import get_logger

from ecg_aggregator.sync.calibration import (
    AlignmentComputer,
    CalibrationCorrelator,
    DeviceAlignment,
    FlashEvent,
)
from ecg_aggregator.sync.spike_detector import AccSample, SpikeDetector, TapEvent
from ecg_aggregator.sync.types import CalibrationSessionStats, DeviceCalibrationStatus

if TYPE_CHECKING:
    from ecg_aggregator.storage.persistence import ECGDatabase

logger = get_logger(__name__)


class CalibrationSession:
    """Manages a single active calibration session.

    Coordinates spike detection, tap-flash correlation, and alignment computation
    in real-time as ACC data and flash events arrive.
    """

    def __init__(
        self,
        session_id: int,
        target_devices: list[str],
        database: ECGDatabase,
    ):
        """Initialize calibration session.

        Args:
            session_id: Unique session identifier
            target_devices: List of device IDs to calibrate
            database: Database instance for persisting alignments
        """
        self.session_id = session_id
        self.target_devices = set(target_devices)
        self.database = database
        self.start_time = time.time()

        # Flash events (in-memory only)
        self.flash_events: list[FlashEvent] = []
        self.flash_id_counter = 0

        # Tap events per device (in-memory only)
        self.device_taps: dict[str, list[TapEvent]] = {
            device_id: [] for device_id in target_devices
        }

        # Current alignments per device (updated incrementally)
        self.device_alignments: dict[str, DeviceAlignment] = {}

        # Calibration components
        self.spike_detector = SpikeDetector(
            threshold=2.0,  # 2G minimum
            min_interval=0.3,  # 300ms between taps
            window_size=50,
        )
        self.correlator = CalibrationCorrelator(
            max_reaction_time=0.5,  # 500ms max reaction
            min_reaction_time=0.05,  # 50ms min reaction
        )
        self.alignment_computer = AlignmentComputer(
            min_pairs=3,  # Need at least 3 taps
            max_error=0.1,  # 100ms max mean error
        )

        logger.info(
            f"Started calibration session {session_id} with {len(target_devices)} target devices"
        )

    def add_flash_event(
        self, flash_timestamp: float, event_type: str = "visual", pattern_id: str | None = None
    ) -> FlashEvent:
        """Record a flash event.

        Args:
            flash_timestamp: Flash timestamp (host time, seconds since epoch)
            event_type: Event type ("visual" or "vibration")
            pattern_id: Pattern identifier (for vibration patterns)

        Returns:
            Created FlashEvent
        """
        self.flash_id_counter += 1
        flash_event = FlashEvent(
            flash_id=self.flash_id_counter,
            flash_timestamp=flash_timestamp,
            event_type=event_type,
            pattern_id=pattern_id,
        )

        self.flash_events.append(flash_event)

        logger.debug(
            f"Flash event {flash_event.flash_id} recorded at {flash_timestamp:.3f} "
            f"(total flashes: {len(self.flash_events)})"
        )

        return flash_event

    def process_acc_sample(
        self, sample: AccSample
    ) -> tuple[TapEvent | None, DeviceAlignment | None]:
        """Process ACC sample in real-time.

        This is called for every ACC sample from the gRPC servicer.
        Only processes samples from target devices.

        Args:
            sample: Accelerometer sample

        Returns:
            Tuple of (tap_event, updated_alignment) if tap detected and matched,
            (None, None) otherwise
        """
        # Only process target devices
        if sample.device_id not in self.target_devices:
            return None, None

        # Run spike detection
        tap_event = self.spike_detector.process_sample(sample)

        if tap_event is None:
            return None, None

        # Tap detected! Store it
        if sample.device_id not in self.device_taps:
            self.device_taps[sample.device_id] = []
        self.device_taps[sample.device_id].append(tap_event)

        # Try to match tap to recent flash events
        matched_pair = self.correlator.match_tap_to_flash(tap_event, self.flash_events)

        if matched_pair is None:
            logger.debug(f"Tap detected but no matching flash for device {sample.device_id}")
            return tap_event, None

        # Update alignment with new matched pair
        existing_alignment = self.device_alignments.get(sample.device_id)
        updated_alignment = self.alignment_computer.update_alignment(
            existing_alignment, matched_pair
        )

        self.device_alignments[sample.device_id] = updated_alignment

        logger.info(
            f"Alignment updated for {sample.device_id}: "
            f"status={updated_alignment.status}, "
            f"confidence={updated_alignment.confidence:.2f}, "
            f"offset={updated_alignment.time_offset:.3f}s, "
            f"taps={updated_alignment.tap_count}"
        )

        return tap_event, updated_alignment

    def get_device_status(self, device_id: str) -> DeviceCalibrationStatus:
        """Get current calibration status for a device.

        Args:
            device_id: Device identifier

        Returns:
            Status dictionary
        """
        alignment = self.device_alignments.get(device_id)

        if alignment is None:
            return {
                "device_id": device_id,
                "status": "waiting_for_taps",
                "confidence": 0.0,
                "tap_count": len(self.device_taps.get(device_id, [])),
                "ready": False,
            }

        return {
            "device_id": device_id,
            "status": alignment.status,
            "confidence": alignment.confidence,
            "tap_count": alignment.tap_count,
            "offset": alignment.time_offset,
            "mean_error": alignment.mean_error,
            "std_error": alignment.std_error,
            "ready": self.is_device_ready(device_id),
        }

    def is_device_ready(self, device_id: str, min_confidence: float = 0.8) -> bool:
        """Check if device has sufficient alignment confidence.

        Args:
            device_id: Device identifier
            min_confidence: Minimum required confidence

        Returns:
            True if device is ready (aligned with sufficient confidence)
        """
        alignment = self.device_alignments.get(device_id)
        if alignment is None:
            return False

        return alignment.status == "aligned" and alignment.confidence >= min_confidence

    def get_ready_devices(self, min_confidence: float = 0.8) -> list[str]:
        """Get list of devices that are aligned and ready.

        Args:
            min_confidence: Minimum required confidence

        Returns:
            List of device IDs that are ready
        """
        return [
            device_id
            for device_id in self.target_devices
            if self.is_device_ready(device_id, min_confidence)
        ]

    def get_all_device_status(self) -> dict[str, DeviceCalibrationStatus]:
        """Get calibration status for all target devices.

        Returns:
            Dictionary mapping device_id to status dict
        """
        return {device_id: self.get_device_status(device_id) for device_id in self.target_devices}

    def finalize(self, offset_versions: dict[str, int] | None = None) -> dict[str, DeviceAlignment]:
        """Finalize calibration session and save alignments to database.

        Args:
            offset_versions: Optional dict mapping device_id to TimeAlignmentService offset_version

        Returns:
            Dictionary of final alignments (device_id -> DeviceAlignment)
        """
        logger.info(f"Finalizing calibration session {self.session_id}")

        # Save all valid alignments to database
        saved_count = 0
        for device_id, alignment in self.device_alignments.items():
            if alignment.status == "aligned" and alignment.confidence >= 0.8:
                offset_version = offset_versions.get(device_id) if offset_versions else None

                success = self.database.save_device_alignment(
                    device_id=device_id,
                    time_offset=alignment.time_offset,
                    confidence=alignment.confidence,
                    tap_count=alignment.tap_count,
                    drift=alignment.drift,
                    mean_error=alignment.mean_error,
                    std_error=alignment.std_error,
                    offset_version=offset_version,
                )

                if success:
                    saved_count += 1
                    logger.info(f"Saved alignment for {device_id} to database")
                else:
                    logger.error(f"Failed to save alignment for {device_id}")

        logger.info(
            f"Session {self.session_id} finalized: "
            f"{saved_count}/{len(self.device_alignments)} alignments saved, "
            f"{len(self.flash_events)} flashes recorded"
        )

        return self.device_alignments

    def get_stats(self) -> CalibrationSessionStats:
        """Get session statistics.

        Returns:
            Statistics dictionary
        """
        return {
            "session_id": self.session_id,
            "start_time": self.start_time,
            "duration": time.time() - self.start_time,
            "target_devices": len(self.target_devices),
            "flash_count": len(self.flash_events),
            "total_taps": sum(len(taps) for taps in self.device_taps.values()),
            "aligned_devices": len(
                [a for a in self.device_alignments.values() if a.status == "aligned"]
            ),
            "ready_devices": len(self.get_ready_devices()),
        }


class CalibrationManager:
    """Global manager for calibration sessions.

    Manages active calibration session and routes ACC samples to spike detector.
    """

    def __init__(self, database: ECGDatabase):
        """Initialize calibration manager.

        Args:
            database: Database instance
        """
        self.database = database
        self.active_session: CalibrationSession | None = None
        self.session_id_counter = 0

        logger.info("Calibration manager initialized")

    def start_session(
        self, target_devices: list[str], name: str | None = None, notes: str | None = None
    ) -> CalibrationSession:
        """Start new calibration session.

        Args:
            target_devices: List of device IDs to calibrate
            name: Optional session name
            notes: Optional session notes

        Returns:
            Created CalibrationSession

        Raises:
            RuntimeError: If a session is already active
        """
        if self.active_session is not None:
            raise RuntimeError(
                f"Calibration session {self.active_session.session_id} is already active"
            )

        self.session_id_counter += 1
        session_id = self.session_id_counter

        self.active_session = CalibrationSession(
            session_id=session_id,
            target_devices=target_devices,
            database=self.database,
        )

        logger.info(
            f"Started calibration session {session_id} (name={name}, devices={len(target_devices)})"
        )

        return self.active_session

    def get_active_session(self) -> CalibrationSession | None:
        """Get currently active session.

        Returns:
            Active CalibrationSession or None
        """
        return self.active_session

    def stop_session(self, offset_versions: dict[str, int] | None = None) -> int | None:
        """Stop and finalize active calibration session.

        Args:
            offset_versions: Optional dict mapping device_id to TimeAlignmentService offset_version

        Returns:
            Session ID that was stopped, or None if no active session
        """
        if self.active_session is None:
            logger.warning("No active calibration session to stop")
            return None

        session_id = self.active_session.session_id

        # Finalize session (saves alignments to DB)
        self.active_session.finalize(offset_versions=offset_versions)

        # Clear active session
        self.active_session = None

        logger.info(f"Stopped calibration session {session_id}")

        return session_id

    def process_acc_sample(
        self, sample: AccSample
    ) -> tuple[TapEvent | None, DeviceAlignment | None]:
        """Process ACC sample through active calibration session.

        This should be called for every ACC sample from the gRPC servicer.

        Args:
            sample: Accelerometer sample

        Returns:
            Tuple of (tap_event, updated_alignment) if tap detected and matched,
            (None, None) otherwise
        """
        if self.active_session is None:
            return None, None

        return self.active_session.process_acc_sample(sample)

    def add_flash_event(
        self, flash_timestamp: float, event_type: str = "visual", pattern_id: str | None = None
    ) -> FlashEvent | None:
        """Add flash event to active session.

        Args:
            flash_timestamp: Flash timestamp (host time, seconds since epoch)
            event_type: Event type ("visual" or "vibration")
            pattern_id: Pattern identifier (for vibration patterns)

        Returns:
            Created FlashEvent or None if no active session
        """
        if self.active_session is None:
            logger.warning("Cannot add flash event: no active calibration session")
            return None

        return self.active_session.add_flash_event(flash_timestamp, event_type, pattern_id)

    def get_session_stats(self) -> CalibrationSessionStats | None:
        """Get statistics for active session.

        Returns:
            Stats dictionary or None if no active session
        """
        if self.active_session is None:
            return None

        return self.active_session.get_stats()
