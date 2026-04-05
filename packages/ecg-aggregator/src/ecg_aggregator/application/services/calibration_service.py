"""Calibration application service."""

import time
from typing import Any

from pydantic import TypeAdapter

from ecg_aggregator.application.dto.calibration import (
    CalibrationCommandResult,
    CalibrationDevicesStatusMessage,
    CalibrationErrorMessage,
    CalibrationFlashRecordedMessage,
    CalibrationInboundMessage,
    CalibrationNoActiveSessionMessage,
    CalibrationOutboundMessage,
    CalibrationSessionActiveMessage,
    CalibrationSessionStartedMessage,
    CalibrationSessionStoppedMessage,
)
from ecg_aggregator.domain.time import HostTimeSeconds
from ecg_aggregator.sync.calibration_manager import CalibrationManager
from ecg_aggregator.sync.time_alignment import TimeAlignmentService


class CalibrationService:
    """Coordinate calibration session use cases."""

    def __init__(
        self,
        calibration_manager: CalibrationManager | None,
        time_alignment: TimeAlignmentService,
    ) -> None:
        """Initialize the calibration service."""
        self._calibration_manager = calibration_manager
        self._time_alignment = time_alignment

    def get_initial_message(self) -> CalibrationOutboundMessage:
        """Build the initial calibration websocket payload."""
        if not self._calibration_manager:
            return CalibrationErrorMessage(message="Calibration manager not available")

        active_session = self._calibration_manager.get_active_session()
        if active_session is None:
            return CalibrationNoActiveSessionMessage(timestamp=HostTimeSeconds(time.time()))

        return CalibrationSessionActiveMessage(
            session_id=active_session.session_id,
            devices=active_session.get_all_device_status(),
            stats=active_session.get_stats(),
        )

    def handle_message(self, message: dict[str, Any]) -> CalibrationCommandResult:
        """Validate and execute an inbound calibration command."""
        if not self._calibration_manager:
            return CalibrationCommandResult(
                response=CalibrationErrorMessage(message="Calibration manager not available"),
                broadcast=False,
            )

        try:
            request: CalibrationInboundMessage = TypeAdapter(
                CalibrationInboundMessage
            ).validate_python(message)
        except Exception as exc:
            return CalibrationCommandResult(
                response=CalibrationErrorMessage(message=f"Invalid message: {exc}"),
                broadcast=False,
            )

        if request.type == "start_session":
            try:
                session = self._calibration_manager.start_session(
                    target_devices=request.target_devices,
                    name=request.name,
                    notes=request.notes,
                )
            except RuntimeError as exc:
                return CalibrationCommandResult(
                    response=CalibrationErrorMessage(message=str(exc)),
                    broadcast=False,
                )

            return CalibrationCommandResult(
                response=CalibrationSessionStartedMessage(
                    session_id=session.session_id,
                    target_devices=list(session.target_devices),
                    start_time=session.start_time,
                ),
                broadcast=True,
            )

        if request.type == "stop_session":
            active_session = self._calibration_manager.get_active_session()
            if active_session is None:
                return CalibrationCommandResult(
                    response=CalibrationErrorMessage(message="No active session to stop"),
                    broadcast=False,
                )

            session_id = self._calibration_manager.stop_session(
                offset_versions=self._time_alignment.get_offset_versions(
                    active_session.target_devices
                )
            )
            if session_id is None:
                return CalibrationCommandResult(
                    response=CalibrationErrorMessage(message="No active session to stop"),
                    broadcast=False,
                )

            return CalibrationCommandResult(
                response=CalibrationSessionStoppedMessage(session_id=session_id),
                broadcast=True,
            )

        if request.type == "flash_event":
            flash_timestamp = request.timestamp or HostTimeSeconds(time.time())
            event_type = request.event_type or "visual"
            flash_event = self._calibration_manager.add_flash_event(
                flash_timestamp=flash_timestamp,
                event_type=event_type,
                pattern_id=request.pattern_id,
            )
            if flash_event is None:
                return CalibrationCommandResult(
                    response=CalibrationErrorMessage(message="No active calibration session"),
                    broadcast=False,
                )

            active_session = self._calibration_manager.get_active_session()
            flash_count = len(active_session.flash_events) if active_session else 0
            return CalibrationCommandResult(
                response=CalibrationFlashRecordedMessage(
                    flash_id=flash_event.flash_id,
                    timestamp=flash_event.flash_timestamp,
                    flash_count=flash_count,
                ),
                broadcast=True,
            )

        active_session = self._calibration_manager.get_active_session()
        if active_session is None:
            return CalibrationCommandResult(
                response=CalibrationNoActiveSessionMessage(timestamp=HostTimeSeconds(time.time())),
                broadcast=False,
            )

        return CalibrationCommandResult(
            response=CalibrationDevicesStatusMessage(
                devices=active_session.get_all_device_status(),
                stats=active_session.get_stats(),
            ),
            broadcast=False,
        )
