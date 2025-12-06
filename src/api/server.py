"""FastAPI server for ECG streaming."""

import asyncio
import time

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from src.api.data_buffer import ECGDataBuffer
from src.collector.adapter_manager import BLEAdapterManager
from src.common.logging import get_logger
from src.sync.time_alignment import TimeAlignmentService

logger = get_logger(__name__)


class ECGStreamingServer:
    """FastAPI server for ECG data streaming."""

    def __init__(
        self,
        adapter_manager: BLEAdapterManager,
        time_alignment: TimeAlignmentService,
        data_buffer: ECGDataBuffer,
        websocket_fps: int = 30,
        cors_origins: list[str] | None = None,
    ):
        """Initialize the server.

        Args:
            adapter_manager: BLE adapter manager instance
            time_alignment: Time alignment service instance
            data_buffer: Data buffer instance
            websocket_fps: WebSocket broadcast rate in FPS
            cors_origins: CORS allowed origins
        """
        self.adapter_manager = adapter_manager
        self.time_alignment = time_alignment
        self.data_buffer = data_buffer
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
            """List all devices and their status."""
            devices = []

            for driver in self.adapter_manager.get_all_devices():
                device_info = await driver.get_device_info()

                # Add sync status
                sync_model = self.time_alignment.get_device_model(driver.device_id)
                if sync_model:
                    device_info["sync"] = {
                        "ready": self.time_alignment.is_device_ready(driver.device_id),
                        "confidence": sync_model.confidence,
                        "drift_ppm": (sync_model.drift - 1.0) * 1_000_000,
                    }
                else:
                    device_info["sync"] = {"ready": False}

                devices.append(device_info)

            return {"devices": devices, "count": len(devices)}

        @self.app.get("/stats")
        async def get_stats() -> dict[str, object]:
            """Get synchronization statistics."""
            sync_stats = self.time_alignment.get_sync_stats()
            adapter_stats = self.adapter_manager.get_adapter_stats()

            return {
                "sync": sync_stats,
                "adapters": adapter_stats,
                "websocket_connections": len(self.active_connections),
            }

        @self.app.get("/buffer/stats")
        async def get_buffer_stats() -> dict:
            """Get data buffer statistics."""
            return self.data_buffer.get_stats()

        @self.app.get("/buffer/latest")
        async def get_latest_samples() -> dict[str, dict]:
            """Get latest sample for each device."""
            return self.data_buffer.get_latest_by_device()

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
    adapter_manager: BLEAdapterManager,
    time_alignment: TimeAlignmentService,
    data_buffer: ECGDataBuffer,
    websocket_fps: int = 30,
    cors_origins: list[str] | None = None,
) -> tuple[FastAPI, ECGStreamingServer]:
    """Create and configure the FastAPI application.

    Args:
        adapter_manager: BLE adapter manager
        time_alignment: Time alignment service
        data_buffer: Data buffer
        websocket_fps: WebSocket broadcast rate
        cors_origins: CORS allowed origins

    Returns:
        Tuple of (FastAPI app, ECGStreamingServer instance)
    """
    server = ECGStreamingServer(
        adapter_manager=adapter_manager,
        time_alignment=time_alignment,
        data_buffer=data_buffer,
        websocket_fps=websocket_fps,
        cors_origins=cors_origins,
    )

    return server.app, server
