"""Author model."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:  # pragma: no cover
    from app.models.book import Book


class Author(TimestampMixin, Base):
    __tablename__ = "authors"
    __table_args__ = (Index("ix_authors_name", "name"),)

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    country: Mapped[str | None] = mapped_column(String(80), nullable=True)

    # Kept unloaded by default: a collection eager-loaded on every author query
    # would be wasteful. Router-layer queries decide when books are needed.
    books: Mapped[list[Book]] = relationship(
        back_populates="author",
        cascade="save-update, merge",
        lazy="raise",
    )
