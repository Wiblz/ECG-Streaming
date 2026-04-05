"""FastAPI server for the aggregator API."""

from ecg_common import __version__
from ecg_common.logging import get_logger
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ecg_aggregator.api.routes import (
    buffer_router,
    calibration_router,
    collectors_router,
    debug_router,
    devices_router,
    realtime_router,
    sessions_router,
    sse_router,
    system_router,
)
from ecg_aggregator.application.runtime import ApplicationRuntime
from ecg_aggregator.infrastructure.realtime.calibration_hub import CalibrationWebSocketHub
from ecg_aggregator.infrastructure.realtime.realtime_ws_hub import RealtimeWebSocketHub
from ecg_aggregator.infrastructure.realtime.sse_hub import SSEHub

logger = get_logger(__name__)


class APIServer:
    """FastAPI server for the aggregator API."""

    def __init__(
        self,
        runtime: ApplicationRuntime,
        realtime_hub: RealtimeWebSocketHub,
        sse_hub: SSEHub,
        calibration_hub: CalibrationWebSocketHub,
        cors_origins: list[str] | None = None,
    ):
        self.runtime = runtime
        self.realtime = realtime_hub
        self.sse_hub = sse_hub
        self.calibration_hub = calibration_hub

        self.app = FastAPI(
            title="ECG Streaming API",
            description="Real-time ECG data streaming from multiple devices",
            version=__version__,
        )

        if cors_origins is None:
            cors_origins = ["*"]

        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        self.app.state.runtime = self.runtime
        self.app.state.sse_hub = self.sse_hub
        self.app.state.realtime_hub = self.realtime
        self.app.state.calibration_hub = self.calibration_hub

        self._register_routes()

    def _register_routes(self) -> None:
        """Register API routes."""
        self.app.include_router(system_router)
        self.app.include_router(devices_router)
        self.app.include_router(sessions_router)
        self.app.include_router(collectors_router)
        self.app.include_router(buffer_router)
        self.app.include_router(debug_router)
        self.app.include_router(sse_router)
        self.app.include_router(realtime_router)
        self.app.include_router(calibration_router)

    async def start_broadcast(self) -> None:
        """Start background broadcast tasks."""
        await self.realtime.start()
        await self.sse_hub.start()
        await self.calibration_hub.start()

    async def stop_broadcast(self) -> None:
        """Stop background broadcast tasks."""
        await self.realtime.stop()
        await self.sse_hub.stop()
        await self.calibration_hub.stop()

    async def shutdown(self) -> None:
        """Shutdown the server and close all connections."""
        logger.info("Shutting down server...")
        await self.realtime.shutdown()
        await self.calibration_hub.close_all()
        logger.info("Server shutdown complete")
