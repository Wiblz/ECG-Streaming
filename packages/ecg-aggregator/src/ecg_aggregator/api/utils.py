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
