"""Author business logic."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import ConflictError, NotFoundError
from app.models import Author
from app.repositories import AuthorRepository
from app.repositories.base import guard_integrity
from app.schemas.author import AuthorCreate, AuthorUpdate

DUPLICATE_AUTHOR_MSG = "Author details conflict with an existing record"


async def list_authors(
    session: AsyncSession, *, q: str | None = None, offset: int = 0, limit: int = 20
) -> tuple[list[Author], int]:
    return await AuthorRepository(session).list(q=q, offset=offset, limit=limit)


async def get_author(session: AsyncSession, author_id: int) -> Author:
    author = await AuthorRepository(session).get(author_id)
    if author is None:
        raise NotFoundError(f"Author {author_id} not found")
    return author


async def get_author_with_books(session: AsyncSession, author_id: int) -> Author:
    """Detail view: the ``books`` collection is explicitly eager-loaded."""
    author = await AuthorRepository(session).get_with_books(author_id)
    if author is None:
        raise NotFoundError(f"Author {author_id} not found")
    return author


async def create_author(session: AsyncSession, payload: AuthorCreate) -> Author:
    repo = AuthorRepository(session)
    async with guard_integrity(session, DUPLICATE_AUTHOR_MSG):
        author = await repo.add(**payload.model_dump())
        await session.commit()
    return author


async def update_author(session: AsyncSession, author_id: int, payload: AuthorUpdate) -> Author:
    repo = AuthorRepository(session)
    author = await get_author(session, author_id)
    values = payload.model_dump(exclude_unset=True)
    if not values:
        return author
    async with guard_integrity(session, DUPLICATE_AUTHOR_MSG):
        author = await repo.save(author, values)
        await session.commit()
    return author


async def delete_author(session: AsyncSession, author_id: int) -> None:
    repo = AuthorRepository(session)
    author = await get_author(session, author_id)
    book_count = await repo.book_count(author_id)
    if book_count:
        raise ConflictError(
            f"Author {author_id} still has {book_count} book(s) and cannot be deleted. "
            "Re-assign or delete those books first."
        )
    await repo.remove(author)
    await session.commit()
