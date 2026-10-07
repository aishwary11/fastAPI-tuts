"""Loan schemas. The loan status is derived, never stored."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field, computed_field

from app.models.enums import LoanStatus
from app.schemas.summaries import BookSummary, MemberSummary, ORMModel


class LoanCreate(BaseModel):
    """A borrow request."""

    book_id: int = Field(gt=0)
    member_id: int = Field(gt=0)


class LoanRead(ORMModel):
    id: int
    book: BookSummary
    member: MemberSummary
    borrowed_at: datetime
    due_at: datetime
    returned_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def status(self) -> LoanStatus:
        if self.returned_at is not None:
            return LoanStatus.RETURNED
        if self.due_at < datetime.now(UTC):
            return LoanStatus.OVERDUE
        return LoanStatus.ACTIVE
