"""Author queries."""

from __future__ import annotations

from sqlalchemy import Select, func, select
from sqlalchemy.orm import selectinload

from app.models import Author, Book
from app.repositories.base import Repository


class AuthorRepository(Repository[Author]):
    model = Author

    @staticmethod
    def _filters(q: str | None) -> list:
        if not q:
            return []
        pattern: str = f"%{q.strip()}%"
        return [Author.name.ilike(pattern)]

    async def list(
        self, *, q: str | None = None, offset: int = 0, limit: int = 20
    ) -> tuple[list[Author], int]:
        clauses = self._filters(q)
        stmt: Select[tuple[Author]] = (
            select(Author)
            .where(*clauses)
            .order_by(Author.name, Author.id)
            .offset(offset)
            .limit(limit)
        )
        items: list[Author] = list((await self.session.execute(stmt)).scalars().all())
        return items, await self.count(*clauses)

    async def get_with_books(self, author_id: int) -> Author | None:
        """Author plus books: ``books`` is ``lazy="raise"``, so load it here."""
        stmt: Select[tuple[Author]] = (
            select(Author).where(Author.id == author_id).options(selectinload(Author.books))
        )
        return (await self.session.execute(stmt)).scalars().unique().one_or_none()

    async def book_count(self, author_id: int) -> int:
        stmt: Select[tuple[int]] = (
            select(func.count()).select_from(Book).where(Book.author_id == author_id)
        )
        return (await self.session.execute(stmt)).scalar_one()
