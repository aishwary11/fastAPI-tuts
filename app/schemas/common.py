"""Pagination helpers shared by every list endpoint."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel

T = TypeVar("T")

MAX_PAGE_SIZE = 100


@dataclass(slots=True)
class PaginationParams:
    """Limit/offset pair, validated at the query-string boundary."""

    limit: int
    offset: int


def pagination_params(
    limit: int = Query(default=20, ge=1, le=MAX_PAGE_SIZE, description="Items per page"),
    offset: int = Query(default=0, ge=0, description="Items to skip"),
) -> PaginationParams:
    return PaginationParams(limit=limit, offset=offset)


class Page(BaseModel, Generic[T]):
    """Envelope for a paginated collection."""

    items: list[T]
    total: int
    limit: int
    offset: int

    @property
    def has_more(self) -> bool:
        return self.offset + len(self.items) < self.total


class Message(BaseModel):
    """Simple acknowledgement body."""

    detail: str
