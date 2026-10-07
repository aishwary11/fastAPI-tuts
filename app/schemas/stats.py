"""Aggregate statistics about the library."""

from __future__ import annotations

from pydantic import BaseModel


class LibraryStats(BaseModel):
    total_authors: int
    total_books: int
    total_copies: int
    available_copies: int
    total_members: int
    active_members: int
    open_loans: int
    overdue_loans: int
    completed_loans: int
