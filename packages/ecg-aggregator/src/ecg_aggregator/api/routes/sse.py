"""SSE routes."""

import asyncio
import time
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.sse import EventSourceResponse, ServerSentEvent

from ecg_aggregator.api.deps import get_runtime, get_sse_hub
from ecg_aggregator.application.dto.realtime import (
    BufferStatsData,
    CollectorStatus,
    CollectorUpdateData,
    ConnectedEventData,
    DeviceUpdateData,
    HeartbeatEventData,
)
from ecg_aggregator.application.runtime import ApplicationRuntime
from ecg_aggregator.domain.time import HostTimeSeconds
from ecg_aggregator.infrastructure.realtime.sse_hub import SSEHub

router = APIRouter(tags=["events"])


@router.get("/events/status", response_class=EventSourceResponse)
async def status_events(
    request: Request,
    sse_hub: Annotated[SSEHub, Depends(get_sse_hub)],
    runtime: Annotated[ApplicationRuntime, Depends(get_runtime)],
) -> AsyncGenerator[ServerSentEvent]:
    """Server-Sent Events endpoint for real-time status updates.

    Streams events for:
    - collector_update: Collector connection/heartbeat/health changes
    - device_update: Device status changes
    - heartbeat: Periodic keepalive (every 30s)
    """
    client_queue = await sse_hub.connect()

    try:
        connected = ConnectedEventData(timestamp=HostTimeSeconds(time.time()))
        yield ServerSentEvent(data=connected, event="connected")

        stats = runtime.system_query_service.get_stats()
        initial_stats = BufferStatsData(
            ecg_buffer=stats.ecg_buffer,
            acc_buffer=stats.acc_buffer,
        )
        yield ServerSentEvent(data=initial_stats, event="buffer_stats")

        # Seed current collector states so clients catch up if collectors were already connected
        for collector in runtime.collector_query_service.list_collectors():
            sse_status: CollectorStatus = (
                "DISCONNECTED" if collector.health == "disconnected" else "HEALTHY"
            )
            initial_collector = CollectorUpdateData(
                collector_id=collector.collector_id,
                display_name=collector.display_name,
                status=sse_status,
                active_devices=collector.active_devices,
                samples_sent=collector.samples_sent,
            )
            yield ServerSentEvent(data=initial_collector, event="collector_update")

        # Seed current device states so clients catch up if devices were already streaming
        for device_status in runtime.device_query_service.list_device_statuses():
            if device_status.collector_id is None:
                continue
            initial_device = DeviceUpdateData(
                device_id=device_status.device_id,
                collector_id=device_status.collector_id,
                status=device_status.status,
                battery_level=device_status.battery_level,
            )
            yield ServerSentEvent(data=initial_device, event="device_update")

        last_heartbeat = time.time()

        while True:
            if await request.is_disconnected():
                break

            try:
                message = await asyncio.wait_for(client_queue.get(), timeout=1.0)
                yield message
            except TimeoutError:
                if time.time() - last_heartbeat > 30:
                    heartbeat = HeartbeatEventData(timestamp=HostTimeSeconds(time.time()))
                    yield ServerSentEvent(data=heartbeat, event="heartbeat")
                    last_heartbeat = time.time()

    except asyncio.CancelledError:
        pass
    finally:
        await sse_hub.disconnect(client_queue)
