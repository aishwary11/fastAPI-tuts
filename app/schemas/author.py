"""Author schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.summaries import BookSummary, ORMModel


class AuthorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    bio: str | None = None
    country: str | None = Field(default=None, max_length=80)


class AuthorUpdate(BaseModel):
    """Every field optional: only the provided keys are applied."""

    name: str | None = Field(default=None, min_length=1, max_length=160)
    bio: str | None = None
    country: str | None = Field(default=None, max_length=80)


class AuthorRead(ORMModel):
    id: int
    name: str
    bio: str | None
    country: str | None
    created_at: datetime
    updated_at: datetime


class AuthorDetail(AuthorRead):
    books: list[BookSummary] = []
