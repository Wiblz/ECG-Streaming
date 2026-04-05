"""Buffer HTTP routes."""

from typing import Annotated

from fastapi import APIRouter, Depends

from ecg_aggregator.api.deps import get_runtime
from ecg_aggregator.application.dto.buffer import (
    BufferedAccelerometerSampleDTO,
    BufferedECGSampleDTO,
)
from ecg_aggregator.application.runtime import ApplicationRuntime
from ecg_aggregator.domain.realtime import BufferStatsSnapshot

router = APIRouter(tags=["buffer"])


@router.get("/buffer/stats", response_model=BufferStatsSnapshot)
async def get_buffer_stats(
    runtime: Annotated[ApplicationRuntime, Depends(get_runtime)],
) -> BufferStatsSnapshot:
    """Get ECG buffer statistics."""
    return BufferStatsSnapshot.model_validate(
        runtime.buffer_query_service.get_ecg_buffer_stats().model_dump()
    )


@router.get("/buffer/latest", response_model=dict[str, BufferedECGSampleDTO])
async def get_latest_samples(
    runtime: Annotated[ApplicationRuntime, Depends(get_runtime)],
) -> dict[str, BufferedECGSampleDTO]:
    """Get latest ECG sample for each device."""
    return {
        device_id: BufferedECGSampleDTO.model_validate(sample.model_dump())
        for device_id, sample in runtime.buffer_query_service.get_latest_ecg_samples().items()
    }


@router.get("/accelerometer/buffer/stats", response_model=BufferStatsSnapshot)
async def get_acc_buffer_stats(
    runtime: Annotated[ApplicationRuntime, Depends(get_runtime)],
) -> BufferStatsSnapshot:
    """Get accelerometer buffer statistics."""
    return BufferStatsSnapshot.model_validate(
        runtime.buffer_query_service.get_acc_buffer_stats().model_dump()
    )


@router.get(
    "/accelerometer/buffer/latest",
    response_model=dict[str, BufferedAccelerometerSampleDTO],
)
async def get_acc_latest_samples(
    runtime: Annotated[ApplicationRuntime, Depends(get_runtime)],
) -> dict[str, BufferedAccelerometerSampleDTO]:
    """Get latest accelerometer sample for each device."""
    return {
        device_id: BufferedAccelerometerSampleDTO.model_validate(sample.model_dump())
        for device_id, sample in runtime.buffer_query_service.get_latest_acc_samples().items()
    }
