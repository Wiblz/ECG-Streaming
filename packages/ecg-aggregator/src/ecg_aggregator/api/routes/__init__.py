"""API router exports."""

from ecg_aggregator.api.routes.buffer import router as buffer_router
from ecg_aggregator.api.routes.calibration import router as calibration_router
from ecg_aggregator.api.routes.collectors import router as collectors_router
from ecg_aggregator.api.routes.debug import router as debug_router
from ecg_aggregator.api.routes.devices import router as devices_router
from ecg_aggregator.api.routes.realtime import router as realtime_router
from ecg_aggregator.api.routes.sessions import router as sessions_router
from ecg_aggregator.api.routes.sse import router as sse_router
from ecg_aggregator.api.routes.system import router as system_router

__all__ = [
    "buffer_router",
    "calibration_router",
    "collectors_router",
    "debug_router",
    "devices_router",
    "realtime_router",
    "sessions_router",
    "sse_router",
    "system_router",
]
