"""Loan queries."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select

from app.models import Loan, LoanStatus
from app.repositories.base import Repository


def _utcnow() -> datetime:
    return datetime.now(UTC)


class LoanRepository(Repository[Loan]):
    model = Loan

    @staticmethod
    def _status_clauses(status: LoanStatus | None, now: datetime) -> list:
        if status is LoanStatus.RETURNED:
            return [Loan.returned_at.is_not(None)]
        if status is LoanStatus.ACTIVE:
            return [Loan.returned_at.is_(None), Loan.due_at >= now]
        if status is LoanStatus.OVERDUE:
            return [Loan.returned_at.is_(None), Loan.due_at < now]
        return []

    @classmethod
    def _filters(
        cls,
        *,
        status: LoanStatus | None = None,
        member_id: int | None = None,
        book_id: int | None = None,
        now: datetime | None = None,
    ) -> list:
        clauses = cls._status_clauses(status, now or _utcnow())
        if member_id is not None:
            clauses.append(Loan.member_id == member_id)
        if book_id is not None:
            clauses.append(Loan.book_id == book_id)
        return clauses

    async def fetch_page(
        self,
        *,
        status: LoanStatus | None = None,
        member_id: int | None = None,
        book_id: int | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[Loan], int]:
        clauses = self._filters(status=status, member_id=member_id, book_id=book_id)
        stmt = (
            select(Loan)
            .where(*clauses)
            .order_by(Loan.borrowed_at.desc(), Loan.id.desc())
            .offset(offset)
            .limit(limit)
        )
        items = list((await self.session.execute(stmt)).scalars().unique().all())
        return items, await self.count(*clauses)

    async def get_open_loan(self, book_id: int, member_id: int) -> Loan | None:
        """The member's currently-open loan of this book, if any."""
        stmt = select(Loan).where(
            Loan.book_id == book_id,
            Loan.member_id == member_id,
            Loan.returned_at.is_(None),
        )
        return (await self.session.execute(stmt)).scalars().unique().one_or_none()

    async def book_loan_count(self, book_id: int) -> int:
        stmt = select(func.count()).select_from(Loan).where(Loan.book_id == book_id)
        return (await self.session.execute(stmt)).scalar_one()

    async def count_by_status(self, status: LoanStatus | None = None) -> int:
        return await self.count(*self._status_clauses(status, _utcnow()))
