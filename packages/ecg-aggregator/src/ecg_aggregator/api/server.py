"""FastAPI server for ECG streaming."""

import asyncio
import contextlib
import json
import time
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from ecg_common import __version__
from ecg_common.logging import get_logger
from fastapi import FastAPI, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sse_starlette.sse import EventSourceResponse

from ecg_aggregator.api.data_buffer import AccelerometerDataBuffer, ECGDataBuffer
from ecg_aggregator.api.models import (
    CollectorInfo,
    CollectorsResponse,
    DeviceNicknameUpdate,
)
from ecg_aggregator.api.sse_broadcaster import SSEBroadcaster
from ecg_aggregator.grpc_server import ECGStreamingServicer
from ecg_aggregator.storage.persistence import ECGDatabase
from ecg_aggregator.sync.calibration_manager import CalibrationManager
from ecg_aggregator.sync.time_alignment import TimeAlignmentService

logger = get_logger(__name__)


def group_samples_by_device(samples: list[dict]) -> dict[str, list[dict]]:
    """Group samples by device_id for bandwidth-efficient transmission.

    Args:
        samples: List of sample dictionaries, each containing a 'device_id' field

    Returns:
        Dictionary mapping device_id to list of samples (with device_id removed)
    """
    devices_data: dict[str, list[dict]] = {}
    for sample in samples:
        device_id = sample["device_id"]
        if device_id not in devices_data:
            devices_data[device_id] = []
        # Remove device_id from sample dict since it's in the key
        sample_without_device_id = {k: v for k, v in sample.items() if k != "device_id"}
        devices_data[device_id].append(sample_without_device_id)
    return devices_data


class ECGStreamingServer:
    """FastAPI server for ECG data streaming."""

    def __init__(
        self,
        time_alignment: TimeAlignmentService,
        ecg_buffer: ECGDataBuffer,
        acc_buffer: AccelerometerDataBuffer,
        database: ECGDatabase,
        grpc_servicer: ECGStreamingServicer | None = None,
        calibration_manager: CalibrationManager | None = None,
        sse_broadcaster: SSEBroadcaster | None = None,
        websocket_fps: int = 30,
        cors_origins: list[str] | None = None,
    ):
        """Initialize the server.

        Args:
            time_alignment: Time alignment service instance
            ecg_buffer: ECG data buffer instance
            acc_buffer: Accelerometer data buffer instance
            database: Database instance
            grpc_servicer: Optional gRPC servicer for accessing device status
            calibration_manager: Optional calibration manager for device alignment
            sse_broadcaster: Optional SSE broadcaster (creates new one if not provided)
            websocket_fps: WebSocket broadcast rate in FPS
            cors_origins: CORS allowed origins
        """
        self.time_alignment = time_alignment
        self.ecg_buffer = ecg_buffer
        self.acc_buffer = acc_buffer
        self.database = database
        self.grpc_servicer = grpc_servicer
        self.calibration_manager = calibration_manager
        self.websocket_fps = websocket_fps
        self.broadcast_interval = 1.0 / websocket_fps

        # WebSocket connections
        self.ecg_connections: list[WebSocket] = []
        self.acc_connections: list[WebSocket] = []
        self.calibration_connections: list[WebSocket] = []

        # SSE broadcaster for status updates
        self.sse_broadcaster = sse_broadcaster or SSEBroadcaster()

        # Create FastAPI app
        self.app = FastAPI(
            title="ECG Streaming API",
            description="Real-time ECG data streaming from multiple devices",
            version="0.1.0",
        )

        # Setup CORS
        if cors_origins is None:
            cors_origins = ["*"]

        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Register routes
        self._register_routes()

        # Background tasks
        self._broadcast_task: asyncio.Task | None = None
        self._acc_broadcast_task: asyncio.Task | None = None
        self._stats_broadcast_task: asyncio.Task | None = None

    def _register_routes(self) -> None:
        """Register API routes."""

        @self.app.get("/")
        async def root() -> dict[str, object]:
            """Root endpoint."""
            return {
                "service": "ECG Streaming API",
                "version": "0.1.0",
                "endpoints": {
                    "websocket_ecg": "/ws/ecg",
                    "websocket_accelerometer": "/ws/accelerometer",
                    "devices": "/devices",
                    "devices_all": "/devices/all",
                    "devices_status": "/devices/status",
                    "device_nickname": "/devices/{device_id}/nickname",
                    "collectors": "/collectors",
                    "stats": "/stats",
                    "ecg_buffer": "/buffer/stats",
                    "ecg_latest": "/buffer/latest",
                    "accelerometer_buffer": "/accelerometer/buffer/stats",
                    "accelerometer_latest": "/accelerometer/buffer/latest",
                    "session_start": "/sessions/start",
                    "session_stop": "/sessions/stop",
                    "session_active": "/sessions/active",
                    "sessions": "/sessions",
                },
            }

        @self.app.get("/devices")
        async def list_devices() -> dict[str, object]:
            """List all devices and their sync status."""
            devices = []

            for device_id in self.time_alignment.get_all_models():
                sync_model = self.time_alignment.get_device_model(device_id)

                device_info = {
                    "device_id": device_id,
                    "sync_ready": self.time_alignment.is_device_ready(device_id),
                }

                if sync_model:
                    device_info["sync"] = {
                        "confidence": sync_model.confidence,
                        "drift_ppm": (sync_model.drift - 1.0) * 1_000_000,
                        "sample_count": sync_model.sample_count,
                    }

                devices.append(device_info)

            return {"devices": devices, "count": len(devices)}

        @self.app.get("/version")
        async def get_version() -> dict[str, str]:
            """Get API version information."""
            return {"version": __version__}

        @self.app.get("/events/status")
        async def status_events(request: Request) -> EventSourceResponse:
            """Server-Sent Events endpoint for real-time status updates.

            Streams events for:
            - collector_update: Collector connection/heartbeat/health changes
            - device_update: Device status changes
            - heartbeat: Periodic keepalive (every 30s)

            The frontend should connect to this endpoint and listen for events
            instead of polling REST endpoints.
            """

            async def event_generator() -> AsyncGenerator[dict[str, str]]:
                """Generate SSE events for this client."""
                # Register this client with the broadcaster
                client_queue = await self.sse_broadcaster.connect()

                try:
                    # Send initial connected event
                    yield {"event": "connected", "data": json.dumps({"timestamp": time.time()})}

                    # Send initial buffer stats immediately
                    initial_stats = {
                        "ecg_buffer": self.ecg_buffer.get_stats(),
                        "acc_buffer": self.acc_buffer.get_stats(),
                    }
                    yield {"event": "buffer_stats", "data": json.dumps(initial_stats)}

                    # Keepalive interval
                    last_heartbeat = time.time()

                    while True:
                        # Check if client disconnected
                        if await request.is_disconnected():
                            break

                        # Try to get an event from the queue (non-blocking)
                        try:
                            message = await asyncio.wait_for(client_queue.get(), timeout=1.0)
                            yield {
                                "event": message["event"],
                                "data": json.dumps(message["data"]),
                            }
                        except TimeoutError:
                            # No events, check if we need to send heartbeat
                            if time.time() - last_heartbeat > 30:
                                yield {
                                    "event": "heartbeat",
                                    "data": json.dumps({"timestamp": time.time()}),
                                }
                                last_heartbeat = time.time()

                except asyncio.CancelledError:
                    logger.debug("SSE client cancelled")
                finally:
                    # Unregister client when connection closes
                    await self.sse_broadcaster.disconnect(client_queue)

            return EventSourceResponse(event_generator())

        @self.app.get("/collectors", response_model=CollectorsResponse)
        async def get_collectors() -> CollectorsResponse:
            """Get all collectors (both connected and known from database).

            Merges current connection status with persistent collector metadata.
            """
            current_time = time.time()

            # Get all known collectors from database
            db_collectors = {c["collector_id"]: c for c in self.database.get_all_collectors()}

            # Get currently connected collectors
            connected_collectors = {}
            if self.grpc_servicer:
                connected_collectors = self.grpc_servicer.collectors

            # Merge all collector IDs
            all_collector_ids = set(db_collectors.keys()) | set(connected_collectors.keys())

            collectors_data: list[CollectorInfo] = []
            for collector_id in all_collector_ids:
                # Build base data
                base_data: dict[str, Any] = {
                    "collector_id": collector_id,
                    "display_name": collector_id,
                    "health": "disconnected",
                    "connected": False,
                }

                # Add database metadata if available
                if collector_id in db_collectors:
                    db_info = db_collectors[collector_id]
                    base_data.update(
                        {
                            "display_name": db_info["display_name"] or collector_id,
                            "version": db_info["version"],
                            "metadata": db_info["metadata"],
                            "first_seen": db_info["first_seen"],
                            "last_seen": db_info["last_seen"],
                            "last_heartbeat": db_info["last_heartbeat"],
                        }
                    )

                # Override with current connection info if connected
                if collector_id in connected_collectors:
                    conn_info = connected_collectors[collector_id]
                    base_data.update(
                        {
                            "display_name": conn_info.get("display_name", collector_id),
                            "device_ids": conn_info.get("device_ids", []),
                            "version": conn_info.get("version"),
                            "metadata": conn_info.get("metadata", {}),
                            "connected_at": conn_info.get("connected_at"),
                            "last_heartbeat": conn_info.get("last_heartbeat", 0),
                            "samples_sent": conn_info.get("samples_sent", 0),
                            "active_devices": conn_info.get("active_devices", 0),
                        }
                    )

                # Calculate connection health
                last_heartbeat = base_data.get("last_heartbeat", 0)
                if last_heartbeat:
                    time_since_heartbeat = current_time - last_heartbeat
                    base_data["time_since_heartbeat"] = time_since_heartbeat

                    # Healthy: < 15s, Warning: 15-30s, Disconnected: > 30s
                    if time_since_heartbeat < 15:
                        health = "healthy"
                    elif time_since_heartbeat < 30:
                        health = "warning"
                    else:
                        health = "disconnected"
                else:
                    health = "disconnected"
                    base_data["time_since_heartbeat"] = None

                base_data["health"] = health
                base_data["connected"] = collector_id in connected_collectors

                collectors_data.append(CollectorInfo(**base_data))

            # Sort by health (healthy first), then by last_heartbeat
            health_order = {"healthy": 0, "warning": 1, "disconnected": 2}
            collectors_data.sort(
                key=lambda c: (
                    health_order.get(c.health, 3),
                    -(c.last_heartbeat or 0),
                )
            )

            return CollectorsResponse(collectors=collectors_data, count=len(collectors_data))

        @self.app.get("/devices/status")
        async def get_device_status() -> dict[str, Any]:
            """Get status of all configured devices (from collectors)."""
            if not self.grpc_servicer:
                return {"devices": [], "count": 0, "error": "gRPC servicer not available"}

            # Build collector lookup for display names
            collector_names = {
                cid: cinfo.get("display_name", cid)
                for cid, cinfo in self.grpc_servicer.collectors.items()
            }

            devices_status = []
            for device_id, status_info in self.grpc_servicer.device_statuses.items():
                collector_id = status_info.get("collector_id")
                devices_status.append(
                    {
                        "device_id": device_id,
                        "collector_id": collector_id,
                        "collector_name": collector_names.get(collector_id, collector_id)
                        if collector_id
                        else None,
                        "status": status_info.get("status"),
                        "last_update": status_info.get("last_update"),
                        "battery_level": status_info.get("battery_level"),
                        "error_message": status_info.get("error_message"),
                    }
                )

            return {"devices": devices_status, "count": len(devices_status)}

        @self.app.get("/devices/all")
        async def get_all_devices() -> dict[str, Any]:
            """Get all known devices from database, including disconnected ones.

            Returns both currently connected devices and previously seen devices from database.
            Merges sync status, connection status, and persistent metadata (like nicknames).
            """
            # Get all devices from database (persistent storage)
            db_devices = {d["device_id"]: d for d in self.database.get_all_devices()}

            # Get current sync status
            sync_devices = {
                device_id: self.time_alignment.get_device_model(device_id)
                for device_id in self.time_alignment.get_all_models()
            }

            # Get current connection status from gRPC
            device_statuses = {}
            if self.grpc_servicer:
                device_statuses = self.grpc_servicer.device_statuses

            # Merge all information
            all_device_ids = (
                set(db_devices.keys()) | set(sync_devices.keys()) | set(device_statuses.keys())
            )

            devices = []
            for device_id in all_device_ids:
                device_info: dict[str, Any] = {"device_id": device_id}

                # Add database metadata
                if device_id in db_devices:
                    device_info.update(
                        {
                            "first_seen": db_devices[device_id]["first_seen"],
                            "last_seen": db_devices[device_id]["last_seen"],
                            "total_samples": db_devices[device_id]["total_samples"],
                            "nickname": db_devices[device_id]["nickname"],
                        }
                    )

                # Add sync status
                if device_id in sync_devices:
                    sync_model = sync_devices[device_id]
                    device_info["sync_ready"] = self.time_alignment.is_device_ready(device_id)
                    if sync_model:
                        device_info["sync"] = {
                            "confidence": sync_model.confidence,
                            "drift_ppm": (sync_model.drift - 1.0) * 1_000_000,
                            "sample_count": sync_model.sample_count,
                        }
                else:
                    device_info["sync_ready"] = False

                # Add connection status
                if device_id in device_statuses:
                    status_info = device_statuses[device_id]
                    device_info.update(
                        {
                            "collector_id": status_info.get("collector_id"),
                            "status": status_info.get("status"),
                            "last_update": status_info.get("last_update"),
                            "battery_level": status_info.get("battery_level"),
                            "error_message": status_info.get("error_message"),
                        }
                    )
                else:
                    device_info["status"] = "DISCONNECTED"

                devices.append(device_info)

            # Sort by last_seen (most recent first), then by device_id
            devices.sort(key=lambda d: (-(d.get("last_seen", 0)), d["device_id"]))

            return {"devices": devices, "count": len(devices)}

        @self.app.put("/devices/{device_id}/nickname")
        async def update_device_nickname(
            device_id: str, update: DeviceNicknameUpdate
        ) -> dict[str, Any]:
            """Update a device's nickname.

            Args:
                device_id: Device identifier
                update: Nickname update request

            Returns:
                Success status and updated device info
            """
            success = self.database.update_device_nickname(device_id, update.nickname)

            if success:
                return {
                    "success": True,
                    "device_id": device_id,
                    "nickname": update.nickname,
                }
            else:
                raise HTTPException(
                    status_code=404,
                    detail=f"Device {device_id} not found. Device must have sent samples before nickname can be set.",
                )

        @self.app.get("/stats")
        async def get_stats() -> dict[str, object]:
            """Get synchronization statistics."""
            sync_stats = self.time_alignment.get_sync_stats()
            grpc_stats = self.grpc_servicer.get_stats() if self.grpc_servicer else {}

            return {
                "sync": sync_stats,
                "grpc": grpc_stats,
                "ecg_websocket_connections": len(self.ecg_connections),
                "acc_websocket_connections": len(self.acc_connections),
                "ecg_buffer": self.ecg_buffer.get_stats(),
                "acc_buffer": self.acc_buffer.get_stats(),
            }

        @self.app.get("/debug/connections")
        @self.app.get("/debug/connections/")
        async def debug_connections() -> dict[str, Any]:
            """Debug endpoint to inspect active WebSocket connections."""
            return {
                "ecg_count": len(self.ecg_connections),
                "acc_count": len(self.acc_connections),
                "ecg_connections": [
                    {
                        "id": id(conn),
                        "client": getattr(conn, "client", None),
                        "headers": dict(conn.headers) if hasattr(conn, "headers") else {},
                    }
                    for conn in self.ecg_connections
                ],
                "acc_connections": [
                    {
                        "id": id(conn),
                        "client": getattr(conn, "client", None),
                        "headers": dict(conn.headers) if hasattr(conn, "headers") else {},
                    }
                    for conn in self.acc_connections
                ],
            }

        @self.app.get("/buffer/stats")
        async def get_buffer_stats() -> dict:
            """Get ECG buffer statistics."""
            return self.ecg_buffer.get_stats()

        @self.app.get("/buffer/latest")
        async def get_latest_samples() -> dict[str, dict]:
            """Get latest ECG sample for each device."""
            return self.ecg_buffer.get_latest_by_device()

        # Accelerometer buffer endpoints

        @self.app.get("/accelerometer/buffer/stats")
        async def get_acc_buffer_stats() -> dict:
            """Get accelerometer buffer statistics."""
            return self.acc_buffer.get_stats()

        @self.app.get("/accelerometer/buffer/latest")
        async def get_acc_latest_samples() -> dict[str, dict]:
            """Get latest accelerometer sample for each device."""
            return self.acc_buffer.get_latest_by_device()

        # Session endpoints

        @self.app.post("/sessions/start")
        async def start_session(notes: str | None = None) -> dict[str, Any]:
            """Start a new recording session and begin persisting samples.

            Args:
                notes: Optional session notes

            Returns:
                Session ID and status
            """
            if not self.grpc_servicer:
                raise HTTPException(
                    status_code=503, detail="gRPC servicer not available for session management"
                )

            session_id = self.grpc_servicer.start_session(notes=notes)

            if session_id == -1:
                active_id = self.grpc_servicer.get_active_session_id()
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot start session: session {active_id} is already active",
                )

            return {
                "success": True,
                "session_id": session_id,
                "message": f"Session {session_id} started. Samples will now be persisted to database.",
            }

        @self.app.post("/sessions/stop")
        async def stop_session() -> dict[str, Any]:
            """Stop the currently active recording session.

            Returns:
                Session ID that was stopped
            """
            if not self.grpc_servicer:
                raise HTTPException(
                    status_code=503, detail="gRPC servicer not available for session management"
                )

            session_id = self.grpc_servicer.stop_session()

            if session_id is None:
                raise HTTPException(status_code=400, detail="No active session to stop")

            return {
                "success": True,
                "session_id": session_id,
                "message": f"Session {session_id} stopped. Samples will no longer be persisted.",
            }

        @self.app.get("/sessions/active")
        async def get_active_session() -> dict[str, Any]:
            """Get the currently active session, if any.

            Returns:
                Active session ID and details, or null if no session is active
            """
            if not self.grpc_servicer:
                return {"active": False, "session_id": None, "error": "gRPC servicer not available"}

            session_id = self.grpc_servicer.get_active_session_id()

            if session_id is None:
                return {"active": False, "session_id": None}

            # Get session details from database
            session = self.database.get_session(session_id)

            return {"active": True, "session_id": session_id, "session": session}

        @self.app.get("/sessions")
        async def list_sessions(limit: int | None = None, offset: int = 0) -> dict[str, Any]:
            """List all recording sessions."""
            sessions = self.database.get_sessions(limit=limit, offset=offset)
            return {"sessions": sessions, "count": len(sessions)}

        @self.app.get("/sessions/{session_id}")
        async def get_session_detail(session_id: int) -> dict[str, Any]:
            """Get details for a specific session."""
            session = self.database.get_session(session_id)
            if not session:
                return {"error": "Session not found"}
            return session

        @self.app.get("/sessions/{session_id}/samples")
        async def get_session_samples_endpoint(
            session_id: int,
            device_id: str | None = None,
            start_time: float | None = None,
            end_time: float | None = None,
            limit: int | None = None,
            offset: int = 0,
        ) -> dict[str, Any]:
            """Get ECG samples for a specific session.

            Args:
                session_id: Session ID
                device_id: Filter by device ID (optional)
                start_time: Start of time range in Unix timestamp (optional)
                end_time: End of time range in Unix timestamp (optional)
                limit: Maximum samples to return (optional)
                offset: Number of samples to skip (optional)
            """
            samples = self.database.get_session_samples(
                session_id=session_id,
                device_id=device_id,
                start_time=start_time,
                end_time=end_time,
                limit=limit,
                offset=offset,
            )

            return {
                "session_id": session_id,
                "devices": group_samples_by_device(samples),
                "count": len(samples),
            }

        @self.app.get("/sessions/{session_id}/accelerometer")
        async def get_session_accelerometer_endpoint(
            session_id: int,
            device_id: str | None = None,
            start_time: float | None = None,
            end_time: float | None = None,
            limit: int | None = None,
            offset: int = 0,
        ) -> dict[str, Any]:
            """Get accelerometer samples for a specific session.

            Args:
                session_id: Session ID
                device_id: Filter by device ID (optional)
                start_time: Start of time range in Unix timestamp (optional)
                end_time: End of time range in Unix timestamp (optional)
                limit: Maximum samples to return (optional)
                offset: Number of samples to skip (optional)
            """
            samples = self.database.get_session_accelerometer_samples(
                session_id=session_id,
                device_id=device_id,
                start_time=start_time,
                end_time=end_time,
                limit=limit,
                offset=offset,
            )

            return {
                "session_id": session_id,
                "devices": group_samples_by_device(samples),
                "count": len(samples),
            }

        @self.app.post("/sessions/backfill")
        async def backfill_sessions(
            gap_threshold: float = 300.0, min_duration: float = 30.0
        ) -> dict[str, Any]:
            """Backfill sessions from existing samples.

            Args:
                gap_threshold: Time gap in seconds to consider a new session (default: 300s)
                min_duration: Minimum session duration in seconds to keep (default: 30s)
            """
            sessions_created = self.database.create_sessions_from_samples(
                gap_threshold=gap_threshold, min_duration=min_duration
            )
            return {
                "success": True,
                "sessions_created": sessions_created,
                "message": f"Created {sessions_created} sessions from existing samples",
            }

        @self.app.delete("/sessions/{session_id}")
        async def delete_session_endpoint(session_id: int) -> dict[str, Any]:
            """Delete a session."""
            success = self.database.delete_session(session_id)
            if success:
                return {"success": True, "message": f"Session {session_id} deleted"}
            return {"success": False, "error": "Failed to delete session"}

        @self.app.get("/sessions/{session_id}/export", response_model=None)
        async def export_session_csv(session_id: int) -> FileResponse:
            """Export a session to CSV format.

            Args:
                session_id: Session ID to export

            Returns:
                CSV file download
            """
            # Create temporary file path
            temp_path = Path(f"/tmp/session_{session_id}.csv")

            # Run blocking I/O in thread pool to avoid blocking event loop
            loop = asyncio.get_event_loop()
            success = await loop.run_in_executor(
                None, self.database.export_session_to_csv, session_id, temp_path
            )

            if not success:
                raise HTTPException(
                    status_code=404, detail=f"Session {session_id} not found or has no data"
                )

            # Return file for download
            return FileResponse(
                path=temp_path,
                media_type="text/csv",
                filename=f"session_{session_id}.csv",
            )

        @self.app.post("/sessions/import")
        async def import_session_csv(file: UploadFile) -> dict[str, Any]:
            """Import a session from CSV format.

            Args:
                file: CSV file upload

            Returns:
                Session ID of imported session
            """
            # Save uploaded file to temporary location
            temp_path = Path(f"/tmp/import_{file.filename}")

            try:
                # Read file content
                content = await file.read()

                # Run blocking I/O in thread pool
                loop = asyncio.get_event_loop()

                # Write file in executor
                await loop.run_in_executor(None, temp_path.write_bytes, content)

                # Import the session in executor
                session_id = await loop.run_in_executor(
                    None, self.database.import_session_from_csv, temp_path
                )

                # Clean up temp file in executor
                await loop.run_in_executor(None, temp_path.unlink)

                if session_id is None:
                    raise HTTPException(status_code=400, detail="Failed to import session from CSV")

                return {
                    "success": True,
                    "session_id": session_id,
                    "message": f"Successfully imported session {session_id}",
                }

            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error handling CSV import: {e}")
                if temp_path.exists():
                    await loop.run_in_executor(None, temp_path.unlink)
                raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}") from e

        @self.app.websocket("/ws/ecg")
        async def websocket_endpoint(websocket: WebSocket) -> None:
            """WebSocket endpoint for real-time ECG streaming."""
            await self._handle_websocket(websocket)

        @self.app.websocket("/ws/accelerometer")
        async def websocket_acc_endpoint(websocket: WebSocket) -> None:
            """WebSocket endpoint for real-time accelerometer streaming."""
            await self._handle_acc_websocket(websocket)

        @self.app.websocket("/ws/calibration")
        async def websocket_calibration_endpoint(websocket: WebSocket) -> None:
            """WebSocket endpoint for calibration session management."""
            await self._handle_calibration_websocket(websocket)

    async def _handle_websocket(self, websocket: WebSocket) -> None:
        """Handle an ECG WebSocket connection.

        Args:
            websocket: WebSocket connection
        """
        await websocket.accept()
        self.ecg_connections.append(websocket)
        logger.info(f"ECG WebSocket connected. Active connections: {len(self.ecg_connections)}")

        try:
            # Send initial state
            devices = self.ecg_buffer.get_device_list()
            await websocket.send_json(
                {
                    "type": "init",
                    "devices": devices,
                    "timestamp": time.time(),
                }
            )

            # Keep connection alive and listen for messages
            while True:
                try:
                    # Receive messages (if client sends any)
                    data = await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
                    # Handle client messages if needed
                    logger.debug(f"Received from client: {data}")
                except TimeoutError:
                    # No message received, continue
                    pass

        except WebSocketDisconnect:
            logger.info("ECG WebSocket disconnected")
        except Exception as e:
            logger.error(f"ECG WebSocket error: {e}")
        finally:
            if websocket in self.ecg_connections:
                self.ecg_connections.remove(websocket)
            logger.info(f"ECG WebSocket closed. Active connections: {len(self.ecg_connections)}")

    async def _handle_acc_websocket(self, websocket: WebSocket) -> None:
        """Handle an accelerometer WebSocket connection.

        Args:
            websocket: WebSocket connection
        """
        await websocket.accept()
        self.acc_connections.append(websocket)
        logger.info(
            f"Accelerometer WebSocket connected. Active connections: {len(self.acc_connections)}"
        )

        try:
            # Send initial state
            devices = self.acc_buffer.get_device_list()
            await websocket.send_json(
                {
                    "type": "init",
                    "devices": devices,
                    "timestamp": time.time(),
                }
            )

            # Keep connection alive and listen for messages
            while True:
                try:
                    # Receive messages (if client sends any)
                    data = await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
                    # Handle client messages if needed
                    logger.debug(f"Received from acc client: {data}")
                except TimeoutError:
                    # No message received, continue
                    pass

        except WebSocketDisconnect:
            logger.info("Accelerometer WebSocket disconnected")
        except Exception as e:
            logger.error(f"Accelerometer WebSocket error: {e}")
        finally:
            if websocket in self.acc_connections:
                self.acc_connections.remove(websocket)
            logger.info(
                f"Accelerometer WebSocket closed. Active connections: {len(self.acc_connections)}"
            )

    async def _handle_calibration_websocket(self, websocket: WebSocket) -> None:
        """Handle calibration WebSocket connection.

        Args:
            websocket: WebSocket connection
        """
        await websocket.accept()
        self.calibration_connections.append(websocket)
        logger.info(
            f"Calibration WebSocket connected. Active connections: {len(self.calibration_connections)}"
        )

        try:
            # Send initial state
            active_session = (
                self.calibration_manager.get_active_session() if self.calibration_manager else None
            )

            if active_session:
                await websocket.send_json(
                    {
                        "type": "session_active",
                        "session_id": active_session.session_id,
                        "devices": active_session.get_all_device_status(),
                        "stats": active_session.get_stats(),
                    }
                )
            else:
                await websocket.send_json(
                    {
                        "type": "no_active_session",
                        "timestamp": time.time(),
                    }
                )

            # Listen for messages from client
            while True:
                try:
                    data = await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
                    message = json.loads(data)

                    # Handle client messages
                    response = await self._handle_calibration_message(message)

                    if response:
                        await websocket.send_json(response)

                        # Broadcast to other calibration clients
                        if response.get("broadcast", False):
                            await self._broadcast_calibration_message(response, exclude=websocket)

                except TimeoutError:
                    # No message received, continue
                    pass
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON from calibration client: {e}")
                    await websocket.send_json({"type": "error", "message": "Invalid JSON format"})

        except WebSocketDisconnect:
            logger.info("Calibration WebSocket disconnected")
        except Exception as e:
            logger.error(f"Calibration WebSocket error: {e}")
        finally:
            if websocket in self.calibration_connections:
                self.calibration_connections.remove(websocket)
            logger.info(
                f"Calibration WebSocket closed. Active connections: {len(self.calibration_connections)}"
            )

    async def _handle_calibration_message(self, message: dict[str, Any]) -> dict[str, Any] | None:
        """Handle incoming calibration WebSocket message.

        Args:
            message: Message from client

        Returns:
            Response to send back (or None)
        """
        if not self.calibration_manager:
            return {"type": "error", "message": "Calibration manager not available"}

        msg_type = message.get("type")

        if msg_type == "start_session":
            # Start new calibration session
            target_devices = message.get("target_devices", [])
            name = message.get("name")
            notes = message.get("notes")

            try:
                session = self.calibration_manager.start_session(
                    target_devices=target_devices,
                    name=name,
                    notes=notes,
                )

                return {
                    "type": "session_started",
                    "session_id": session.session_id,
                    "target_devices": list(session.target_devices),
                    "start_time": session.start_time,
                    "broadcast": True,
                }

            except RuntimeError as e:
                return {"type": "error", "message": str(e)}

        elif msg_type == "stop_session":
            # Stop active session
            # Get offset versions from TimeAlignmentService
            offset_versions = {}
            if self.grpc_servicer:
                for device_id in self.grpc_servicer.device_statuses:
                    model = self.time_alignment._device_models.get(device_id)
                    if model:
                        offset_versions[device_id] = model.offset_version

            session_id = self.calibration_manager.stop_session(offset_versions=offset_versions)

            if session_id is None:
                return {"type": "error", "message": "No active session to stop"}

            return {
                "type": "session_stopped",
                "session_id": session_id,
                "broadcast": True,
            }

        elif msg_type == "flash_event":
            # Record flash event
            flash_timestamp = message.get("timestamp", time.time())
            event_type = message.get("event_type", "visual")
            pattern_id = message.get("pattern_id")

            flash_event = self.calibration_manager.add_flash_event(
                flash_timestamp=flash_timestamp,
                event_type=event_type,
                pattern_id=pattern_id,
            )

            if flash_event is None:
                return {"type": "error", "message": "No active calibration session"}

            active_session = self.calibration_manager.active_session
            flash_count = len(active_session.flash_events) if active_session else 0

            return {
                "type": "flash_recorded",
                "flash_id": flash_event.flash_id,
                "timestamp": flash_event.flash_timestamp,
                "flash_count": flash_count,
                "broadcast": True,
            }

        elif msg_type == "get_status":
            # Get current session status
            active_session = self.calibration_manager.get_active_session()

            if active_session is None:
                return {
                    "type": "no_active_session",
                    "timestamp": time.time(),
                }

            return {
                "type": "devices_status",
                "devices": active_session.get_all_device_status(),
                "stats": active_session.get_stats(),
            }

        return None

    async def _broadcast_calibration_message(
        self, message: dict[str, Any], exclude: WebSocket | None = None
    ) -> None:
        """Broadcast message to all calibration WebSocket clients.

        Args:
            message: Message to broadcast
            exclude: WebSocket to exclude from broadcast
        """
        # Remove broadcast flag before sending
        broadcast_msg = {k: v for k, v in message.items() if k != "broadcast"}

        disconnected = []
        for connection in self.calibration_connections:
            if connection == exclude:
                continue

            try:
                await connection.send_json(broadcast_msg)
            except Exception as e:
                logger.error(f"Error broadcasting to calibration WebSocket: {e}")
                disconnected.append(connection)

        # Remove disconnected clients
        for connection in disconnected:
            if connection in self.calibration_connections:
                self.calibration_connections.remove(connection)

    async def broadcast_data(self) -> None:
        """Broadcast ECG data to all connected WebSocket clients."""
        last_broadcast_time: dict[str, float] = {}
        broadcast_count = 0

        while True:
            try:
                await asyncio.sleep(self.broadcast_interval)

                if not self.ecg_connections:
                    logger.debug("[BROADCAST] No WebSocket connections, skipping")
                    continue

                current_time = time.time()

                # Get new samples since last broadcast for each device
                all_samples = []
                devices = self.ecg_buffer.get_device_list()
                logger.debug(f"[BROADCAST] Checking {len(devices)} devices for new samples")

                for device_id in devices:
                    since = last_broadcast_time.get(device_id, current_time - 1.0)
                    samples = self.ecg_buffer.get_recent_samples(since=since, device_id=device_id)
                    logger.debug(
                        f"[BROADCAST] Device {device_id}: got {len(samples)} samples since {since:.2f}"
                    )
                    if samples:
                        all_samples.extend(samples)
                        last_broadcast_time[device_id] = samples[-1]["global_time"]

                if not all_samples:
                    buffer_stats = self.ecg_buffer.get_stats()
                    logger.debug(
                        f"[BROADCAST] No samples to broadcast. Buffer stats: {buffer_stats}"
                    )
                    continue

                # Group samples by device_id for bandwidth efficiency
                devices_data = group_samples_by_device(all_samples)

                broadcast_count += 1
                logger.debug(
                    f"[BROADCAST] Broadcasting {len(all_samples)} samples from {len(devices_data)} devices (broadcast #{broadcast_count})"
                )

                # Broadcast to all connections - grouped by device_id
                message = {
                    "type": "data",
                    "devices": devices_data,
                    "timestamp": current_time,
                    "count": len(all_samples),
                }

                # Send to all connections concurrently
                disconnected = []
                for connection in self.ecg_connections:
                    try:
                        await connection.send_json(message)
                    except Exception as e:
                        logger.error(f"Error sending to ECG WebSocket: {e}")
                        disconnected.append(connection)

                # Remove disconnected clients
                for connection in disconnected:
                    if connection in self.ecg_connections:
                        self.ecg_connections.remove(connection)

            except Exception as e:
                logger.error(f"Error in ECG broadcast loop: {e}")
                await asyncio.sleep(1.0)

    async def broadcast_acc_data(self) -> None:
        """Broadcast accelerometer data to all connected WebSocket clients."""
        last_broadcast_time: dict[str, float] = {}

        while True:
            try:
                await asyncio.sleep(self.broadcast_interval)

                if not self.acc_connections:
                    continue

                current_time = time.time()

                # Get new samples since last broadcast for each device
                all_samples = []
                for device_id in self.acc_buffer.get_device_list():
                    since = last_broadcast_time.get(device_id, current_time - 1.0)
                    samples = self.acc_buffer.get_recent_samples(since=since, device_id=device_id)
                    if samples:
                        all_samples.extend(samples)
                        last_broadcast_time[device_id] = samples[-1]["global_time"]

                if not all_samples:
                    continue

                # Group samples by device_id for bandwidth efficiency
                devices_data = group_samples_by_device(all_samples)

                # Broadcast to all connections - grouped by device_id
                message = {
                    "type": "data",
                    "devices": devices_data,
                    "timestamp": current_time,
                    "count": len(all_samples),
                }

                # Send to all connections concurrently
                disconnected = []
                for connection in self.acc_connections:
                    try:
                        await connection.send_json(message)
                    except Exception as e:
                        logger.error(f"Error sending to accelerometer WebSocket: {e}")
                        disconnected.append(connection)

                # Remove disconnected clients
                for connection in disconnected:
                    if connection in self.acc_connections:
                        self.acc_connections.remove(connection)

            except Exception as e:
                logger.error(f"Error in accelerometer broadcast loop: {e}")
                await asyncio.sleep(1.0)

    async def broadcast_buffer_stats(self) -> None:
        """Periodically broadcast buffer statistics via SSE."""
        while True:
            try:
                await asyncio.sleep(1.0)  # Broadcast every second

                if self.sse_broadcaster.get_client_count() == 0:
                    continue  # No clients, skip

                stats = {
                    "ecg_buffer": self.ecg_buffer.get_stats(consume_rate=True),
                    "acc_buffer": self.acc_buffer.get_stats(consume_rate=True),
                }

                await self.sse_broadcaster.broadcast("buffer_stats", stats)  # type: ignore[arg-type]

            except asyncio.CancelledError:
                logger.info("Buffer stats broadcast task cancelled")
                break
            except Exception as e:
                logger.error(f"Error in buffer stats broadcast loop: {e}")
                await asyncio.sleep(1.0)

    async def start_broadcast(self) -> None:
        """Start the background broadcast tasks for ECG, accelerometer, and stats."""
        if self._broadcast_task is None or self._broadcast_task.done():
            self._broadcast_task = asyncio.create_task(self.broadcast_data())
            logger.info(f"Started ECG WebSocket broadcast at {self.websocket_fps} FPS")

        if self._acc_broadcast_task is None or self._acc_broadcast_task.done():
            self._acc_broadcast_task = asyncio.create_task(self.broadcast_acc_data())
            logger.info(f"Started accelerometer WebSocket broadcast at {self.websocket_fps} FPS")

        if self._stats_broadcast_task is None or self._stats_broadcast_task.done():
            self._stats_broadcast_task = asyncio.create_task(self.broadcast_buffer_stats())
            logger.info("Started buffer stats SSE broadcast (every 5s)")

    async def stop_broadcast(self) -> None:
        """Stop the background broadcast tasks."""
        if self._broadcast_task and not self._broadcast_task.done():
            self._broadcast_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._broadcast_task
            logger.info("Stopped ECG WebSocket broadcast")

        if self._acc_broadcast_task and not self._acc_broadcast_task.done():
            self._acc_broadcast_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._acc_broadcast_task
            logger.info("Stopped accelerometer WebSocket broadcast")

        if self._stats_broadcast_task and not self._stats_broadcast_task.done():
            self._stats_broadcast_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._stats_broadcast_task
            logger.info("Stopped buffer stats SSE broadcast")

    async def shutdown(self) -> None:
        """Shutdown the server and close all connections."""
        logger.info("Shutting down server...")

        # Stop broadcasts
        await self.stop_broadcast()

        # Close all ECG WebSocket connections
        for connection in self.ecg_connections.copy():
            try:
                await connection.close()
            except Exception as e:
                logger.error(f"Error closing ECG WebSocket: {e}")

        self.ecg_connections.clear()

        # Close all accelerometer WebSocket connections
        for connection in self.acc_connections.copy():
            try:
                await connection.close()
            except Exception as e:
                logger.error(f"Error closing accelerometer WebSocket: {e}")

        self.acc_connections.clear()

        # Close all calibration WebSocket connections
        for connection in self.calibration_connections.copy():
            try:
                await connection.close()
            except Exception as e:
                logger.error(f"Error closing calibration WebSocket: {e}")

        self.calibration_connections.clear()
        logger.info("Server shutdown complete")

    async def broadcast_calibration_event(self, event_type: str, data: dict[str, Any]) -> None:
        """Broadcast calibration event to all calibration WebSocket clients.

        Args:
            event_type: Event type
            data: Event data
        """
        if not self.calibration_connections:
            return

        message = {
            "type": event_type,
            **data,
        }

        disconnected = []
        for connection in self.calibration_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error broadcasting calibration event: {e}")
                disconnected.append(connection)

        # Remove disconnected clients
        for connection in disconnected:
            if connection in self.calibration_connections:
                self.calibration_connections.remove(connection)


def create_app(
    time_alignment: TimeAlignmentService,
    ecg_buffer: ECGDataBuffer,
    acc_buffer: AccelerometerDataBuffer,
    database: ECGDatabase,
    grpc_servicer: ECGStreamingServicer | None = None,
    calibration_manager: CalibrationManager | None = None,
    websocket_fps: int = 30,
    cors_origins: list[str] | None = None,
) -> tuple[FastAPI, ECGStreamingServer]:
    """Create and configure the FastAPI application.

    Args:
        time_alignment: Time alignment service
        ecg_buffer: ECG data buffer
        acc_buffer: Accelerometer data buffer
        database: Database instance
        grpc_servicer: Optional gRPC servicer for device status
        calibration_manager: Optional calibration manager for device alignment
        websocket_fps: WebSocket broadcast rate
        cors_origins: CORS allowed origins

    Returns:
        Tuple of (FastAPI app, ECGStreamingServer instance)
    """
    server = ECGStreamingServer(
        time_alignment=time_alignment,
        ecg_buffer=ecg_buffer,
        acc_buffer=acc_buffer,
        database=database,
        calibration_manager=calibration_manager,
        grpc_servicer=grpc_servicer,
        websocket_fps=websocket_fps,
        cors_origins=cors_origins,
    )

    return server.app, server
