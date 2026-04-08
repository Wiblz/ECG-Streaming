"""Collector HTTP routes."""

from typing import Annotated

from fastapi import APIRouter, Depends

from ecg_aggregator.api.deps import get_runtime
from ecg_aggregator.api.models import CollectorInfo, CollectorsResponse
from ecg_aggregator.application.runtime import ApplicationRuntime

router = APIRouter(tags=["collectors"])


@router.get("/collectors", response_model=CollectorsResponse)
async def get_collectors(
    runtime: Annotated[ApplicationRuntime, Depends(get_runtime)],
) -> CollectorsResponse:
    """Get all collectors, both connected and known from the database."""
    collectors = [
        CollectorInfo(
            collector_id=dto.collector_id,
            display_name=dto.display_name,
            device_ids=dto.device_ids,
            version=dto.version,
            collector_type=dto.collector_type,
            first_seen=dto.first_seen,
            last_seen=dto.last_seen,
            connected_at=dto.connected_at,
            samples_sent=dto.samples_sent,
            active_devices=dto.active_devices,
            health=dto.health,
            connected=dto.connected,
        )
        for dto in runtime.collector_query_service.list_collectors()
    ]
    return CollectorsResponse(collectors=collectors)
