"""Compact nested representations used inside other response bodies.

These live in their own module so that ``book``, ``author`` and ``loan``
schemas can embed each other without circular imports.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ORMModel(BaseModel):
    """Base for every response schema that mirrors an ORM instance."""

    model_config = ConfigDict(from_attributes=True)


class AuthorSummary(ORMModel):
    id: int
    name: str


class BookSummary(ORMModel):
    id: int
    title: str
    isbn: str | None = None
    available_copies: int


class MemberSummary(ORMModel):
    id: int
    full_name: str
    email: str
