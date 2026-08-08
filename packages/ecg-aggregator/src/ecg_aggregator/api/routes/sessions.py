"""Session HTTP routes."""

import asyncio
from functools import partial
from pathlib import Path
from typing import Annotated

from ecg_common.logging import get_logger
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from ecg_aggregator.api.deps import get_runtime
from ecg_aggregator.api.models import (
    ActiveSessionResponse,
    DeleteSessionResponse,
    ImportSessionResponse,
    SessionAccelerometerSamplesResponse,
    SessionActionResponse,
    SessionInfo,
    SessionSamplesResponse,
    SessionsResponse,
)
from ecg_aggregator.api.utils import PaginationParams, pagination_params
from ecg_aggregator.application.dto.query import (
    AccelerometerSessionSampleDTO,
    ECGSessionSampleDTO,
)
from ecg_aggregator.application.runtime import ApplicationRuntime
from ecg_aggregator.application.services.session_service import (
    NoActiveSessionError,
    SessionAlreadyActiveError,
    SessionPersistenceError,
)
from ecg_aggregator.domain.queries import SessionSortField, SortOrder

logger = get_logger(__name__)
router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("/start", response_model=SessionActionResponse)
async def start_session(
    runtime: Annotated[ApplicationRuntime, Depends(get_runtime)],
    notes: str | None = None,
) -> SessionActionResponse:
    """Start a new recording session and begin persisting samples."""
    loop = asyncio.get_running_loop()
    try:
        session_id = await loop.run_in_executor(None, runtime.session_service.start_session, notes)
    except SessionAlreadyActiveError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SessionPersistenceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return SessionActionResponse(
        success=True,
        session_id=session_id,
        message=f"Session {session_id} started. Samples will now be persisted to database.",
    )


@router.post("/stop", response_model=SessionActionResponse)
async def stop_session(
    runtime: Annotated[ApplicationRuntime, Depends(get_runtime)],
) -> SessionActionResponse:
    """Stop the currently active recording session."""
    try:
        session_id = await runtime.session_service.stop_session()
    except NoActiveSessionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SessionPersistenceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return SessionActionResponse(
        success=True,
        session_id=session_id,
        message=f"Session {session_id} stopped. Samples will no longer be persisted.",
    )


@router.get("/active", response_model=ActiveSessionResponse)
async def get_active_session(
    runtime: Annotated[ApplicationRuntime, Depends(get_runtime)],
) -> ActiveSessionResponse:
    """Get the currently active session, if any."""
    session_id = runtime.session_service.get_active_session_id()
    if session_id is None:
        return ActiveSessionResponse(active=False, session_id=None)

    loop = asyncio.get_running_loop()
    session_info_dto = await loop.run_in_executor(
        None, runtime.session_query_service.get_session, session_id
    )
    session_info = (
        SessionInfo.model_validate(session_info_dto.model_dump()) if session_info_dto else None
    )
    return ActiveSessionResponse(active=True, session_id=session_id, session=session_info)


@router.get("", response_model=SessionsResponse)
async def list_sessions(
    runtime: Annotated[ApplicationRuntime, Depends(get_runtime)],
    pagination: Annotated[PaginationParams, Depends(pagination_params)],
    search: str | None = None,
    active: bool | None = None,
    has_notes: bool | None = None,
    device_id: str | None = None,
    sort_by: SessionSortField = "start_time",
    sort_order: SortOrder = SortOrder.DESC,
) -> SessionsResponse:
    """List all recording sessions."""
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        partial(
            runtime.session_query_service.list_sessions,
            limit=pagination.limit,
            offset=pagination.offset,
            search=search,
            active=active,
            has_notes=has_notes,
            device_id=device_id,
            sort_by=sort_by,
            sort_order=sort_order,
        ),
    )
    session_models = [SessionInfo.model_validate(session.model_dump()) for session in result.items]
    return SessionsResponse(
        sessions=session_models,
        count=len(session_models),
        total=result.total,
        limit=result.limit,
        offset=result.offset,
    )


@router.get("/{session_id}", response_model=SessionInfo)
async def get_session_detail(
    session_id: int,
    runtime: Annotated[ApplicationRuntime, Depends(get_runtime)],
) -> SessionInfo:
    """Get details for a specific session."""
    loop = asyncio.get_running_loop()
    session = await loop.run_in_executor(
        None, runtime.session_query_service.get_session, session_id
    )
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    return SessionInfo.model_validate(session.model_dump())


@router.get("/{session_id}/samples", response_model=SessionSamplesResponse)
async def get_session_samples_endpoint(
    session_id: int,
    runtime: Annotated[ApplicationRuntime, Depends(get_runtime)],
    device_id: str | None = None,
    start_time: float | None = None,
    end_time: float | None = None,
    limit: Annotated[
        int, Query(ge=0, description="Maximum number of samples to return; 0 disables the cap.")
    ] = 500_000,
    offset: int = 0,
) -> SessionSamplesResponse:
    """Get ECG samples for a specific session.

    Defaults to at most 500,000 samples (roughly an hour of 130 Hz ECG) to
    bound response size; pass an explicit larger limit or limit=0 for more.
    """
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        partial(
            runtime.session_query_service.get_ecg_samples,
            session_id=session_id,
            device_id=device_id,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            offset=offset,
        ),
    )
    return SessionSamplesResponse(
        session_id=result.session_id,
        devices={
            device: [ECGSessionSampleDTO.model_validate(sample.model_dump()) for sample in samples]
            for device, samples in result.devices.items()
        },
        count=result.count,
    )


@router.get(
    "/{session_id}/accelerometer",
    response_model=SessionAccelerometerSamplesResponse,
)
async def get_session_accelerometer_endpoint(
    session_id: int,
    runtime: Annotated[ApplicationRuntime, Depends(get_runtime)],
    device_id: str | None = None,
    start_time: float | None = None,
    end_time: float | None = None,
    limit: Annotated[
        int, Query(ge=0, description="Maximum number of samples to return; 0 disables the cap.")
    ] = 500_000,
    offset: int = 0,
) -> SessionAccelerometerSamplesResponse:
    """Get accelerometer samples for a specific session.

    Defaults to at most 500,000 samples to bound response size; pass an
    explicit larger limit or limit=0 for more.
    """
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        partial(
            runtime.session_query_service.get_accelerometer_samples,
            session_id=session_id,
            device_id=device_id,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            offset=offset,
        ),
    )
    return SessionAccelerometerSamplesResponse(
        session_id=result.session_id,
        devices={
            device: [
                AccelerometerSessionSampleDTO.model_validate(sample.model_dump())
                for sample in samples
            ]
            for device, samples in result.devices.items()
        },
        count=result.count,
    )


@router.delete("/{session_id}", response_model=DeleteSessionResponse)
async def delete_session_endpoint(
    session_id: int,
    runtime: Annotated[ApplicationRuntime, Depends(get_runtime)],
) -> DeleteSessionResponse:
    """Delete a session."""
    loop = asyncio.get_running_loop()
    success = await loop.run_in_executor(
        None, runtime.session_query_service.delete_session, session_id
    )
    if success:
        return DeleteSessionResponse(success=True, message=f"Session {session_id} deleted")
    return DeleteSessionResponse(success=False, error="Failed to delete session")


@router.get("/{session_id}/export", response_model=None)
async def export_session_csv(
    session_id: int,
    runtime: Annotated[ApplicationRuntime, Depends(get_runtime)],
) -> FileResponse:
    """Export a session to CSV format."""
    temp_path = Path(f"/tmp/session_{session_id}.csv")
    loop = asyncio.get_running_loop()
    success = await loop.run_in_executor(
        None,
        runtime.session_query_service.export_session_to_csv,
        session_id,
        temp_path,
    )
    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Session {session_id} not found or has no data",
        )

    return FileResponse(
        path=temp_path,
        media_type="text/csv",
        filename=f"session_{session_id}.csv",
    )


@router.post("/import", response_model=ImportSessionResponse)
async def import_session_csv(
    file: UploadFile,
    runtime: Annotated[ApplicationRuntime, Depends(get_runtime)],
) -> ImportSessionResponse:
    """Import a session from CSV format."""
    temp_path = Path(f"/tmp/import_{file.filename}")

    try:
        content = await file.read()
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, temp_path.write_bytes, content)
        session_id = await loop.run_in_executor(
            None,
            runtime.session_query_service.import_session_from_csv,
            temp_path,
        )
        await loop.run_in_executor(None, temp_path.unlink)

        if session_id is None:
            raise HTTPException(status_code=400, detail="Failed to import session from CSV")

        return ImportSessionResponse(
            success=True,
            session_id=session_id,
            message=f"Successfully imported session {session_id}",
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Error handling CSV import: {exc}")
        if temp_path.exists():
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, temp_path.unlink)
        raise HTTPException(status_code=500, detail=f"Import failed: {exc}") from exc
