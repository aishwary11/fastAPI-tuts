"""Member endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Query, status

from app.api.deps import PageDep, SessionDep
from app.models import LoanStatus, MemberStatus
from app.schemas.common import Message, Page
from app.schemas.loan import LoanRead
from app.schemas.member import MemberCreate, MemberRead, MemberUpdate
from app.services import circulation as circulation_service
from app.services import members as service

router = APIRouter(prefix="/members", tags=["members"])


@router.get("", response_model=Page[MemberRead], summary="List / search members")
async def list_members(
    session: SessionDep,
    page: PageDep,
    q: str | None = Query(default=None, max_length=160, description="Search name or email"),
    member_status: MemberStatus | None = Query(
        default=None, alias="status", description="Filter by membership status"
    ),
):
    items, total = await service.list_members(
        session, q=q, status=member_status, offset=page.offset, limit=page.limit
    )
    return Page(items=items, total=total, limit=page.limit, offset=page.offset)


@router.post(
    "",
    response_model=MemberRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register a member",
)
async def create_member(session: SessionDep, payload: MemberCreate):
    return await service.create_member(session, payload)


@router.get("/{member_id}", response_model=MemberRead, summary="Get a member")
async def get_member(session: SessionDep, member_id: int):
    return await service.get_member(session, member_id)


@router.get(
    "/{member_id}/loans",
    response_model=Page[LoanRead],
    summary="Borrowing history for a member",
)
async def list_member_loans(
    session: SessionDep,
    page: PageDep,
    member_id: int,
    loan_status: LoanStatus | None = Query(default=None, alias="status"),
):
    # 404s first if the member does not exist.
    await service.get_member(session, member_id)
    items, total = await circulation_service.list_loans(
        session,
        member_id=member_id,
        status=loan_status,
        offset=page.offset,
        limit=page.limit,
    )
    return Page(items=items, total=total, limit=page.limit, offset=page.offset)


@router.patch("/{member_id}", response_model=MemberRead, summary="Update a member")
async def update_member(session: SessionDep, member_id: int, payload: MemberUpdate):
    return await service.update_member(session, member_id, payload)


@router.delete("/{member_id}", response_model=Message, summary="Delete a member")
async def delete_member(session: SessionDep, member_id: int):
    await service.delete_member(session, member_id)
    return Message(detail=f"Member {member_id} deleted")
