"""Book business logic."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import ConflictError, NotFoundError, ValidationError
from app.models import Book
from app.repositories import AuthorRepository, BookRepository, LoanRepository
from app.repositories.base import guard_integrity
from app.schemas.book import BookCreate, BookUpdate

DUPLICATE_ISBN_MSG = "A book with this ISBN already exists"


async def list_books(
    session: AsyncSession,
    *,
    q: str | None = None,
    author_id: int | None = None,
    genre: str | None = None,
    available_only: bool = False,
    offset: int = 0,
    limit: int = 20,
) -> tuple[list[Book], int]:
    return await BookRepository(session).list(
        q=q,
        author_id=author_id,
        genre=genre,
        available_only=available_only,
        offset=offset,
        limit=limit,
    )


async def get_book(session: AsyncSession, book_id: int) -> Book:
    book = await BookRepository(session).get(book_id)
    if book is None:
        raise NotFoundError(f"Book {book_id} not found")
    return book


async def list_genres(session: AsyncSession) -> list[str]:
    return await BookRepository(session).distinct_genres()


async def create_book(session: AsyncSession, payload: BookCreate) -> Book:
    if await AuthorRepository(session).get(payload.author_id) is None:
        raise ValidationError(f"Author {payload.author_id} does not exist")

    books = BookRepository(session)
    if payload.isbn and await books.get_by_isbn(payload.isbn) is not None:
        raise ConflictError(DUPLICATE_ISBN_MSG)

    async with guard_integrity(session, DUPLICATE_ISBN_MSG):
        book = await books.add(
            title=payload.title,
            isbn=payload.isbn,
            genre=payload.genre,
            published_year=payload.published_year,
            author_id=payload.author_id,
            total_copies=payload.total_copies,
            # A brand-new title has every copy on the shelf.
            available_copies=payload.total_copies,
        )
        await session.commit()
    return book


async def update_book(session: AsyncSession, book_id: int, payload: BookUpdate) -> Book:
    books = BookRepository(session)
    book = await get_book(session, book_id)
    values = payload.model_dump(exclude_unset=True)
    if not values:
        return book

    if "author_id" in values and await AuthorRepository(session).get(values["author_id"]) is None:
        raise ValidationError(f"Author {values['author_id']} does not exist")

    if "isbn" in values and values["isbn"]:
        existing = await books.get_by_isbn(values["isbn"])
        if existing is not None and existing.id != book_id:
            raise ConflictError(DUPLICATE_ISBN_MSG)

    if "total_copies" in values:
        # Copies that are currently checked out must survive the recount.
        on_loan = book.total_copies - book.available_copies
        if values["total_copies"] < on_loan:
            raise ValidationError(
                f"{on_loan} copy/copies of this book are currently on loan; "
                f"total_copies cannot be reduced below {on_loan}."
            )
        values["available_copies"] = values["total_copies"] - on_loan

    async with guard_integrity(session, DUPLICATE_ISBN_MSG):
        book = await books.save(book, values)
        await session.commit()
    return book


async def delete_book(session: AsyncSession, book_id: int) -> None:
    books = BookRepository(session)
    book = await get_book(session, book_id)

    loan_count = await LoanRepository(session).book_loan_count(book_id)
    if loan_count:
        raise ConflictError(
            f"Book {book_id} has {loan_count} loan record(s) in its history and cannot "
            "be deleted. Keep the record instead of removing it."
        )
    if book.available_copies < book.total_copies:  # pragma: no cover - defensive
        raise ConflictError(f"Book {book_id} still has copies on loan.")

    await books.remove(book)
    await session.commit()
