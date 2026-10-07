"""Book model."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:  # pragma: no cover
    from app.models.author import Author


class Book(TimestampMixin, Base):
    __tablename__ = "books"
    __table_args__ = (
        CheckConstraint("total_copies > 0", name="total_copies_positive"),
        CheckConstraint("available_copies >= 0", name="available_copies_non_negative"),
        CheckConstraint(
            "available_copies <= total_copies",
            name="available_copies_within_total",
        ),
        Index("ix_books_title", "title"),
        Index("ix_books_author_id", "author_id"),
    )

    title: Mapped[str] = mapped_column(String(300), nullable=False)
    isbn: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True)
    genre: Mapped[str | None] = mapped_column(String(80), nullable=True)
    published_year: Mapped[int | None] = mapped_column(Integer, nullable=True)

    total_copies: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    available_copies: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    author_id: Mapped[int] = mapped_column(
        ForeignKey("authors.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # Many-to-one, non-nullable FK: an inner join keeps `SELECT ... FOR UPDATE`
    # legal when a book row is locked during a borrow.
    author: Mapped[Author] = relationship(
        back_populates="books",
        lazy="joined",
        innerjoin=True,
    )

    @property
    def is_available(self) -> bool:
        return self.available_copies > 0
