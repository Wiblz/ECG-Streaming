"""FastAPI server for ECG streaming."""

import asyncio
import time
from typing import Any

from ecg_common.logging import get_logger
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from ecg_aggregator.api.data_buffer import ECGDataBuffer
from ecg_aggregator.storage.persistence import ECGDatabase
from ecg_aggregator.sync.time_alignment import TimeAlignmentService

logger = get_logger(__name__)


class ECGStreamingServer:
    """FastAPI server for ECG data streaming."""

    def __init__(
        self,
        time_alignment: TimeAlignmentService,
        data_buffer: ECGDataBuffer,
        database: ECGDatabase,
        websocket_fps: int = 30,
        cors_origins: list[str] | None = None,
    ):
        """Initialize the server.

        Args:
            time_alignment: Time alignment service instance
            data_buffer: Data buffer instance
            database: Database instance
            websocket_fps: WebSocket broadcast rate in FPS
            cors_origins: CORS allowed origins
        """
        self.time_alignment = time_alignment
        self.data_buffer = data_buffer
        self.database = database
        self.websocket_fps = websocket_fps
        self.broadcast_interval = 1.0 / websocket_fps

        # WebSocket connections
        self.active_connections: list[WebSocket] = []

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

        # Background task
        self._broadcast_task: asyncio.Task | None = None

    def _register_routes(self) -> None:
        """Register API routes."""

        @self.app.get("/")
        async def root() -> dict[str, object]:
            """Root endpoint."""
            return {
                "service": "ECG Streaming API",
                "version": "0.1.0",
                "endpoints": {
                    "websocket": "/ws/ecg",
                    "devices": "/devices",
                    "stats": "/stats",
                    "buffer": "/buffer/stats",
                },
            }

        @self.app.get("/devices")
        async def list_devices() -> dict[str, object]:
            """List all devices and their sync status."""
            devices = []

            for device_id in self.time_alignment.get_all_models().keys():
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

        @self.app.get("/stats")
        async def get_stats() -> dict[str, object]:
            """Get synchronization statistics."""
            sync_stats = self.time_alignment.get_sync_stats()

            return {
                "sync": sync_stats,
                "websocket_connections": len(self.active_connections),
                "buffer": self.data_buffer.get_stats(),
            }

        @self.app.get("/debug/connections")
        @self.app.get("/debug/connections/")
        async def debug_connections() -> dict[str, Any]:
            """Debug endpoint to inspect active WebSocket connections."""
            return {
                "count": len(self.active_connections),
                "connections": [
                    {
                        "id": id(conn),
                        "client": getattr(conn, "client", None),
                        "headers": dict(conn.headers) if hasattr(conn, "headers") else {},
                    }
                    for conn in self.active_connections
                ],
            }

        @self.app.get("/buffer/stats")
        async def get_buffer_stats() -> dict:
            """Get data buffer statistics."""
            return self.data_buffer.get_stats()

        @self.app.get("/buffer/latest")
        async def get_latest_samples() -> dict[str, dict]:
            """Get latest sample for each device."""
            return self.data_buffer.get_latest_by_device()

        # Session endpoints

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
            """Get samples for a specific session.

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
                "samples": samples,
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

        @self.app.websocket("/ws/ecg")
        async def websocket_endpoint(websocket: WebSocket) -> None:
            """WebSocket endpoint for real-time ECG streaming."""
            await self._handle_websocket(websocket)

    async def _handle_websocket(self, websocket: WebSocket) -> None:
        """Handle a WebSocket connection.

        Args:
            websocket: WebSocket connection
        """
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connected. Active connections: {len(self.active_connections)}")

        try:
            # Send initial state
            devices = self.data_buffer.get_device_list()
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
            logger.info("WebSocket disconnected")
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
        finally:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
            logger.info(f"WebSocket closed. Active connections: {len(self.active_connections)}")

    async def broadcast_data(self) -> None:
        """Broadcast data to all connected WebSocket clients."""
        last_broadcast_time: dict[str, float] = {}

        while True:
            try:
                await asyncio.sleep(self.broadcast_interval)

                if not self.active_connections:
                    continue

                current_time = time.time()

                # Get new samples since last broadcast for each device
                all_samples = []
                for device_id in self.data_buffer.get_device_list():
                    since = last_broadcast_time.get(device_id, current_time - 1.0)
                    samples = self.data_buffer.get_recent_samples(since=since, device_id=device_id)
                    all_samples.extend(samples)
                    if samples:
                        last_broadcast_time[device_id] = samples[-1]["global_time"]

                if not all_samples:
                    continue

                # Broadcast to all connections
                message = {
                    "type": "data",
                    "samples": all_samples,
                    "timestamp": current_time,
                    "count": len(all_samples),
                }

                # Send to all connections concurrently
                disconnected = []
                for connection in self.active_connections:
                    try:
                        await connection.send_json(message)
                    except Exception as e:
                        logger.error(f"Error sending to WebSocket: {e}")
                        disconnected.append(connection)

                # Remove disconnected clients
                for connection in disconnected:
                    if connection in self.active_connections:
                        self.active_connections.remove(connection)

            except Exception as e:
                logger.error(f"Error in broadcast loop: {e}")
                await asyncio.sleep(1.0)

    async def start_broadcast(self) -> None:
        """Start the background broadcast task."""
        if self._broadcast_task is None or self._broadcast_task.done():
            self._broadcast_task = asyncio.create_task(self.broadcast_data())
            logger.info(f"Started WebSocket broadcast at {self.websocket_fps} FPS")

    async def stop_broadcast(self) -> None:
        """Stop the background broadcast task."""
        if self._broadcast_task and not self._broadcast_task.done():
            self._broadcast_task.cancel()
            try:
                await self._broadcast_task
            except asyncio.CancelledError:
                pass
            logger.info("Stopped WebSocket broadcast")

    async def shutdown(self) -> None:
        """Shutdown the server and close all connections."""
        logger.info("Shutting down server...")

        # Stop broadcast
        await self.stop_broadcast()

        # Close all WebSocket connections
        for connection in self.active_connections.copy():
            try:
                await connection.close()
            except Exception as e:
                logger.error(f"Error closing WebSocket: {e}")

        self.active_connections.clear()
        logger.info("Server shutdown complete")


def create_app(
    time_alignment: TimeAlignmentService,
    data_buffer: ECGDataBuffer,
    database: ECGDatabase,
    websocket_fps: int = 30,
    cors_origins: list[str] | None = None,
) -> tuple[FastAPI, ECGStreamingServer]:
    """Create and configure the FastAPI application.

    Args:
        time_alignment: Time alignment service
        data_buffer: Data buffer
        database: Database instance
        websocket_fps: WebSocket broadcast rate
        cors_origins: CORS allowed origins

    Returns:
        Tuple of (FastAPI app, ECGStreamingServer instance)
    """
    server = ECGStreamingServer(
        time_alignment=time_alignment,
        data_buffer=data_buffer,
        database=database,
        websocket_fps=websocket_fps,
        cors_origins=cors_origins,
    )

    return server.app, server
