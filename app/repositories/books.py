"""Book queries."""

from __future__ import annotations

from sqlalchemy import or_, select

from app.models import Author, Book
from app.repositories.base import Repository


class BookRepository(Repository[Book]):
    model = Book

    @staticmethod
    def _filters(
        *,
        q: str | None = None,
        author_id: int | None = None,
        genre: str | None = None,
        available_only: bool = False,
    ) -> list:
        clauses: list = []
        if q and q.strip():
            pattern = f"%{q.strip()}%"
            clauses.append(
                or_(
                    Book.title.ilike(pattern),
                    Book.isbn.ilike(pattern),
                    Book.author.has(Author.name.ilike(pattern)),
                )
            )
        if author_id is not None:
            clauses.append(Book.author_id == author_id)
        if genre:
            clauses.append(Book.genre.ilike(genre.strip()))
        if available_only:
            clauses.append(Book.available_copies > 0)
        return clauses

    async def list(
        self,
        *,
        q: str | None = None,
        author_id: int | None = None,
        genre: str | None = None,
        available_only: bool = False,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[Book], int]:
        clauses = self._filters(
            q=q, author_id=author_id, genre=genre, available_only=available_only
        )
        stmt = (
            select(Book).where(*clauses).order_by(Book.title, Book.id).offset(offset).limit(limit)
        )
        items = list((await self.session.execute(stmt)).scalars().unique().all())
        return items, await self.count(*clauses)

    async def get_by_isbn(self, isbn: str) -> Book | None:
        stmt = select(Book).where(Book.isbn == isbn)
        return (await self.session.execute(stmt)).scalars().unique().one_or_none()

    async def distinct_genres(self) -> list[str]:
        stmt = select(Book.genre).where(Book.genre.is_not(None)).distinct().order_by(Book.genre)
        genres = (await self.session.execute(stmt)).scalars().all()
        # The query already excludes NULLs; this narrows the type for callers.
        return [genre for genre in genres if genre is not None]
