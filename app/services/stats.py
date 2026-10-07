"""Library-wide aggregate statistics."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Book, LoanStatus, Member, MemberStatus
from app.repositories import AuthorRepository, BookRepository, LoanRepository, MemberRepository
from app.schemas.stats import LibraryStats


async def library_stats(session: AsyncSession) -> LibraryStats:
    totals = (
        await session.execute(
            select(
                func.coalesce(func.sum(Book.total_copies), 0),
                func.coalesce(func.sum(Book.available_copies), 0),
            )
        )
    ).one()

    loans = LoanRepository(session)
    members = MemberRepository(session)

    return LibraryStats(
        total_authors=await AuthorRepository(session).count(),
        total_books=await BookRepository(session).count(),
        total_copies=int(totals[0]),
        available_copies=int(totals[1]),
        total_members=await members.count(),
        active_members=await members.count(Member.status == MemberStatus.ACTIVE),
        open_loans=(
            await loans.count_by_status(LoanStatus.ACTIVE)
            + await loans.count_by_status(LoanStatus.OVERDUE)
        ),
        overdue_loans=await loans.count_by_status(LoanStatus.OVERDUE),
        completed_loans=await loans.count_by_status(LoanStatus.RETURNED),
    )
