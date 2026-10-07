"""Author endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Query, status

from app.api.deps import PageDep, SessionDep
from app.schemas.author import AuthorCreate, AuthorDetail, AuthorRead, AuthorUpdate
from app.schemas.common import Message, Page
from app.services import authors as service

router = APIRouter(prefix="/authors", tags=["authors"])


@router.get("", response_model=Page[AuthorRead], summary="List authors")
async def list_authors(
    session: SessionDep,
    page: PageDep,
    q: str | None = Query(default=None, max_length=160, description="Filter by name"),
):
    items, total = await service.list_authors(session, q=q, offset=page.offset, limit=page.limit)
    return Page(items=items, total=total, limit=page.limit, offset=page.offset)


@router.post(
    "",
    response_model=AuthorRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create an author",
)
async def create_author(session: SessionDep, payload: AuthorCreate):
    return await service.create_author(session, payload)


@router.get("/{author_id}", response_model=AuthorDetail, summary="Get an author and their books")
async def get_author(session: SessionDep, author_id: int):
    return await service.get_author_with_books(session, author_id)


@router.patch("/{author_id}", response_model=AuthorRead, summary="Update an author")
async def update_author(session: SessionDep, author_id: int, payload: AuthorUpdate):
    return await service.update_author(session, author_id, payload)


@router.delete("/{author_id}", response_model=Message, summary="Delete an author")
async def delete_author(session: SessionDep, author_id: int):
    await service.delete_author(session, author_id)
    return Message(detail=f"Author {author_id} deleted")
