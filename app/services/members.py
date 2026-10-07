"""Member business logic."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import ConflictError, NotFoundError
from app.models import Member, MemberStatus
from app.repositories import MemberRepository
from app.repositories.base import guard_integrity
from app.schemas.member import MemberCreate, MemberUpdate

DUPLICATE_EMAIL_MSG = "A member with this email already exists"


async def list_members(
    session: AsyncSession,
    *,
    q: str | None = None,
    status: MemberStatus | None = None,
    offset: int = 0,
    limit: int = 20,
) -> tuple[list[Member], int]:
    return await MemberRepository(session).list(q=q, status=status, offset=offset, limit=limit)


async def get_member(session: AsyncSession, member_id: int) -> Member:
    member = await MemberRepository(session).get(member_id)
    if member is None:
        raise NotFoundError(f"Member {member_id} not found")
    return member


async def create_member(session: AsyncSession, payload: MemberCreate) -> Member:
    repo = MemberRepository(session)
    if await repo.get_by_email(payload.email) is not None:
        raise ConflictError(DUPLICATE_EMAIL_MSG)

    async with guard_integrity(session, DUPLICATE_EMAIL_MSG):
        member = await repo.add(
            full_name=payload.full_name,
            email=payload.email.lower(),
            phone=payload.phone,
            status=payload.status,
        )
        await session.commit()
    return member


async def update_member(session: AsyncSession, member_id: int, payload: MemberUpdate) -> Member:
    repo = MemberRepository(session)
    member = await get_member(session, member_id)
    values = payload.model_dump(exclude_unset=True)
    if not values:
        return member

    if "email" in values and values["email"]:
        existing = await repo.get_by_email(values["email"])
        if existing is not None and existing.id != member_id:
            raise ConflictError(DUPLICATE_EMAIL_MSG)
        values["email"] = values["email"].lower()

    async with guard_integrity(session, DUPLICATE_EMAIL_MSG):
        member = await repo.save(member, values)
        await session.commit()
    return member


async def delete_member(session: AsyncSession, member_id: int) -> None:
    repo = MemberRepository(session)
    member = await get_member(session, member_id)

    open_loans = await repo.open_loan_count(member_id)
    if open_loans:
        raise ConflictError(
            f"Member {member_id} has {open_loans} book(s) on loan. "
            "Return them before deleting the member."
        )
    if await repo.total_loan_count(member_id):
        raise ConflictError(
            f"Member {member_id} has borrowing history and cannot be deleted. "
            f"Set status to '{MemberStatus.INACTIVE.value}' instead."
        )

    await repo.remove(member)
    await session.commit()
