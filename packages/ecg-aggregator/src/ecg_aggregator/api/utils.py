"""API helper utilities."""

from typing import Annotated

from fastapi import Query
from pydantic import BaseModel


class PaginationParams(BaseModel):
    """Shared pagination parameters for collection endpoints."""

    limit: int | None = None
    offset: int = 0


def pagination_params(
    limit: Annotated[int | None, Query(ge=0)] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PaginationParams:
    """Parse pagination query parameters into a reusable model."""
    return PaginationParams(limit=limit, offset=offset)


def paginate_items[ItemT](
    items: list[ItemT], pagination: PaginationParams
) -> tuple[list[ItemT], int]:
    """Apply offset/limit pagination to an in-memory list."""
    paginated_items = items[pagination.offset :]
    if pagination.limit is not None:
        paginated_items = paginated_items[: pagination.limit]
    return paginated_items, len(items)


def group_samples_by_device[SampleModelT: BaseModel](
    samples: list[dict], model: type[SampleModelT]
) -> dict[str, list[SampleModelT]]:
    """Group samples by device_id for bandwidth-efficient transmission.

    Args:
        samples: List of sample dictionaries, each containing a 'device_id' field
        model: Pydantic model to validate each sample (device_id will be removed)

    Returns:
        Dictionary mapping device_id to list of samples (with device_id removed)
    """
    devices_data: dict[str, list[SampleModelT]] = {}
    for sample in samples:
        device_id = sample["device_id"]
        if device_id not in devices_data:
            devices_data[device_id] = []
        sample_without_device_id = {k: v for k, v in sample.items() if k != "device_id"}
        devices_data[device_id].append(model.model_validate(sample_without_device_id))
    return devices_data
