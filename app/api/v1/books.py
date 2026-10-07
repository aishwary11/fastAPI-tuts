"""Book endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Query, status

from app.api.deps import PageDep, SessionDep
from app.schemas.book import BookCreate, BookRead, BookUpdate
from app.schemas.common import Message, Page
from app.services import books as service

router = APIRouter(prefix="/books", tags=["books"])


@router.get("", response_model=Page[BookRead], summary="List / search books")
async def list_books(
    session: SessionDep,
    page: PageDep,
    q: str | None = Query(
        default=None, max_length=300, description="Search title, ISBN or author name"
    ),
    author_id: int | None = Query(default=None, gt=0),
    genre: str | None = Query(default=None, max_length=80),
    available_only: bool = Query(default=False, description="Only books with a free copy"),
):
    items, total = await service.list_books(
        session,
        q=q,
        author_id=author_id,
        genre=genre,
        available_only=available_only,
        offset=page.offset,
        limit=page.limit,
    )
    return Page(items=items, total=total, limit=page.limit, offset=page.offset)


@router.get("/genres", response_model=list[str], summary="List all genres in use")
async def list_genres(session: SessionDep):
    return await service.list_genres(session)


@router.post(
    "",
    response_model=BookRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a book to the catalogue",
)
async def create_book(session: SessionDep, payload: BookCreate):
    return await service.create_book(session, payload)


@router.get("/{book_id}", response_model=BookRead, summary="Get a book")
async def get_book(session: SessionDep, book_id: int):
    return await service.get_book(session, book_id)


@router.patch("/{book_id}", response_model=BookRead, summary="Update a book")
async def update_book(session: SessionDep, book_id: int, payload: BookUpdate):
    return await service.update_book(session, book_id, payload)


@router.delete("/{book_id}", response_model=Message, summary="Remove a book")
async def delete_book(session: SessionDep, book_id: int):
    await service.delete_book(session, book_id)
    return Message(detail=f"Book {book_id} deleted")
