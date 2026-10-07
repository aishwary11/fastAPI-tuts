"""Loan model: the record of a member borrowing a book."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:  # pragma: no cover
    from app.models.book import Book
    from app.models.member import Member


class Loan(TimestampMixin, Base):
    """A single borrow event. ``returned_at IS NULL`` means the book is out."""

    __tablename__ = "loans"
    __table_args__ = (
        Index("ix_loans_book_id", "book_id"),
        Index("ix_loans_member_id", "member_id"),
        Index("ix_loans_due_at", "due_at"),
        # Business rule enforced by the database: a member may not hold two
        # open loans for the same book. Guarded in the service layer too, but
        # this makes the invariant race-proof.
        Index(
            "uq_loans_active_book_member",
            "book_id",
            "member_id",
            unique=True,
            postgresql_where=text("returned_at IS NULL"),
            sqlite_where=text("returned_at IS NULL"),
        ),
    )

    book_id: Mapped[int] = mapped_column(
        ForeignKey("books.id", ondelete="RESTRICT"), nullable=False
    )
    member_id: Mapped[int] = mapped_column(
        ForeignKey("members.id", ondelete="RESTRICT"), nullable=False
    )

    borrowed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    returned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    book: Mapped[Book] = relationship(lazy="joined", innerjoin=True)
    member: Mapped[Member] = relationship(lazy="joined", innerjoin=True)
