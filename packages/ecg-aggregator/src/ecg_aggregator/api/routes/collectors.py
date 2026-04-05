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
        CollectorInfo.model_validate(collector.model_dump())
        for collector in runtime.collector_query_service.list_collectors()
    ]
    return CollectorsResponse(collectors=collectors, count=len(collectors))
