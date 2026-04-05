"""SSE routes."""

import asyncio
import json
import time
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sse_starlette.sse import EventSourceResponse

from ecg_aggregator.api.deps import get_runtime, get_sse_hub
from ecg_aggregator.application.dto.realtime import (
    BufferStatsData,
    ConnectedEventData,
    HeartbeatEventData,
)
from ecg_aggregator.application.runtime import ApplicationRuntime
from ecg_aggregator.domain.time import HostTimeSeconds
from ecg_aggregator.infrastructure.realtime.sse_hub import SSEHub

router = APIRouter(tags=["events"])


@router.get("/events/status")
async def status_events(
    request: Request,
    sse_hub: Annotated[SSEHub, Depends(get_sse_hub)],
    runtime: Annotated[ApplicationRuntime, Depends(get_runtime)],
) -> EventSourceResponse:
    """Server-Sent Events endpoint for real-time status updates.

    Streams events for:
    - collector_update: Collector connection/heartbeat/health changes
    - device_update: Device status changes
    - heartbeat: Periodic keepalive (every 30s)
    """

    async def event_generator() -> AsyncGenerator[dict[str, str]]:
        client_queue = await sse_hub.connect()

        try:
            connected = ConnectedEventData(timestamp=HostTimeSeconds(time.time()))
            yield {"event": "connected", "data": json.dumps(connected.model_dump())}

            stats = runtime.system_query_service.get_stats()
            initial_stats = BufferStatsData(
                ecg_buffer=stats.ecg_buffer,
                acc_buffer=stats.acc_buffer,
            )
            yield {"event": "buffer_stats", "data": json.dumps(initial_stats.model_dump())}

            last_heartbeat = time.time()

            while True:
                if await request.is_disconnected():
                    break

                try:
                    message = await asyncio.wait_for(client_queue.get(), timeout=1.0)
                    yield {
                        "event": message["event"],
                        "data": json.dumps(message["data"]),
                    }
                except TimeoutError:
                    if time.time() - last_heartbeat > 30:
                        heartbeat = HeartbeatEventData(timestamp=HostTimeSeconds(time.time()))
                        yield {
                            "event": "heartbeat",
                            "data": json.dumps(heartbeat.model_dump()),
                        }
                        last_heartbeat = time.time()

        except asyncio.CancelledError:
            pass
        finally:
            await sse_hub.disconnect(client_queue)

    return EventSourceResponse(event_generator())
