"""Book schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.summaries import AuthorSummary, ORMModel

ISBN_PATTERN = r"^(?:\d{9}[\dXx]|\d{13})$"


class BookCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    author_id: int = Field(gt=0)
    isbn: str | None = Field(default=None, pattern=ISBN_PATTERN)
    genre: str | None = Field(default=None, max_length=80)
    published_year: int | None = Field(default=None, ge=1000, le=2100)
    total_copies: int = Field(default=1, ge=1, le=10_000)

    @field_validator("isbn", mode="before")
    @classmethod
    def _strip_isbn_separators(cls, value: object) -> object:
        # Run before the pattern check so "978-0-306-40615-7" is accepted.
        if isinstance(value, str):
            return value.replace("-", "").replace(" ", "")
        return value


class BookUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    isbn: str | None = Field(default=None, pattern=ISBN_PATTERN)
    genre: str | None = Field(default=None, max_length=80)
    published_year: int | None = Field(default=None, ge=1000, le=2100)
    total_copies: int | None = Field(default=None, ge=1, le=10_000)
    author_id: int | None = Field(default=None, gt=0)

    @field_validator("isbn", mode="before")
    @classmethod
    def _strip_isbn_separators(cls, value: object) -> object:
        if isinstance(value, str):
            return value.replace("-", "").replace(" ", "")
        return value


class BookRead(ORMModel):
    id: int
    title: str
    isbn: str | None
    genre: str | None
    published_year: int | None
    total_copies: int
    available_copies: int
    is_available: bool
    author: AuthorSummary
    created_at: datetime
    updated_at: datetime
