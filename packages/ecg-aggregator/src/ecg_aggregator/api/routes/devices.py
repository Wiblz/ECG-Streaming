"""Device HTTP routes."""

import asyncio
from functools import partial
from typing import Annotated

from ecg_common import DeviceStatus
from fastapi import APIRouter, Depends, HTTPException

from ecg_aggregator.api.deps import get_runtime
from ecg_aggregator.api.models import (
    DeviceInfo,
    DeviceNicknameUpdate,
    DevicesAllResponse,
    DevicesStatusResponse,
    DevicesSummaryResponse,
    DeviceStatusInfo,
    DeviceSummary,
    UpdateNicknameResponse,
)
from ecg_aggregator.api.utils import PaginationParams, pagination_params
from ecg_aggregator.application.runtime import ApplicationRuntime
from ecg_aggregator.domain.queries import DeviceListSortField, DeviceSummarySortField, SortOrder

router = APIRouter(prefix="/devices", tags=["devices"])


@router.get("", response_model=DevicesSummaryResponse)
async def list_devices(
    runtime: Annotated[ApplicationRuntime, Depends(get_runtime)],
    pagination: Annotated[PaginationParams, Depends(pagination_params)],
    search: str | None = None,
    sync_ready: bool | None = None,
    show_simulated: bool = False,
    sort_by: DeviceSummarySortField = "device_id",
    sort_order: SortOrder = SortOrder.ASC,
) -> DevicesSummaryResponse:
    """List all devices and their sync status."""
    result = runtime.device_query_service.list_device_summaries(
        limit=pagination.limit,
        offset=pagination.offset,
        search=search,
        sync_ready=sync_ready,
        show_simulated=show_simulated,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    paginated_devices = [
        DeviceSummary.model_validate(device.model_dump()) for device in result.items
    ]
    return DevicesSummaryResponse(
        devices=paginated_devices,
        count=len(paginated_devices),
        total=result.total,
        limit=result.limit,
        offset=result.offset,
    )


@router.get("/status", response_model=DevicesStatusResponse)
async def get_device_status(
    runtime: Annotated[ApplicationRuntime, Depends(get_runtime)],
) -> DevicesStatusResponse:
    """Get status of all configured devices (from collectors)."""
    devices_status = [
        DeviceStatusInfo.model_validate(device_status.model_dump())
        for device_status in runtime.device_query_service.list_device_statuses()
    ]
    return DevicesStatusResponse(devices=devices_status, count=len(devices_status))


@router.get("/all", response_model=DevicesAllResponse)
async def get_all_devices(
    runtime: Annotated[ApplicationRuntime, Depends(get_runtime)],
    pagination: Annotated[PaginationParams, Depends(pagination_params)],
    search: str | None = None,
    sync_ready: bool | None = None,
    show_simulated: bool = False,
    status: DeviceStatus | None = None,
    collector_id: str | None = None,
    has_nickname: bool | None = None,
    sort_by: DeviceListSortField = "last_seen",
    sort_order: SortOrder = SortOrder.DESC,
) -> DevicesAllResponse:
    """Get all known devices, including disconnected ones."""
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        partial(
            runtime.device_query_service.list_all_devices,
            limit=pagination.limit,
            offset=pagination.offset,
            search=search,
            sync_ready=sync_ready,
            show_simulated=show_simulated,
            status=status,
            collector_id=collector_id,
            has_nickname=has_nickname,
            sort_by=sort_by,
            sort_order=sort_order,
        ),
    )
    paginated_devices = [DeviceInfo.model_validate(device.model_dump()) for device in result.items]
    return DevicesAllResponse(
        devices=paginated_devices,
        count=len(paginated_devices),
        total=result.total,
        limit=result.limit,
        offset=result.offset,
    )


@router.put("/{device_id}/nickname", response_model=UpdateNicknameResponse)
async def update_device_nickname(
    device_id: str,
    update: DeviceNicknameUpdate,
    runtime: Annotated[ApplicationRuntime, Depends(get_runtime)],
) -> UpdateNicknameResponse:
    """Update a device's nickname."""
    loop = asyncio.get_running_loop()
    success = await loop.run_in_executor(
        None, runtime.device_query_service.update_device_nickname, device_id, update.nickname
    )
    if success:
        return UpdateNicknameResponse(
            success=True,
            device_id=device_id,
            nickname=update.nickname,
        )

    raise HTTPException(
        status_code=404,
        detail=(
            f"Device {device_id} not found. Device must have sent samples before "
            "nickname can be set."
        ),
    )
