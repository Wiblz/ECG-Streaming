"""Domain-owned query and sorting types."""

from enum import StrEnum
from typing import Literal


class SortOrder(StrEnum):
    """Shared sort direction."""

    ASC = "asc"
    DESC = "desc"


SessionSortField = Literal["id", "start_time", "end_time", "device_count", "sample_count"]

DeviceSummarySortField = Literal["device_id", "sync_ready", "confidence", "sample_count"]

DeviceListSortField = Literal[
    "last_seen",
    "first_seen",
    "total_samples",
    "device_id",
    "nickname",
    "status",
    "last_update",
]
