"""Member queries."""

from __future__ import annotations

from sqlalchemy import func, or_, select

from app.models import Loan, Member, MemberStatus
from app.repositories.base import Repository


class MemberRepository(Repository[Member]):
    model = Member

    @staticmethod
    def _filters(*, q: str | None = None, status: MemberStatus | None = None) -> list:
        clauses: list = []
        if q and q.strip():
            pattern = f"%{q.strip()}%"
            clauses.append(or_(Member.full_name.ilike(pattern), Member.email.ilike(pattern)))
        if status is not None:
            clauses.append(Member.status == status)
        return clauses

    async def list(
        self,
        *,
        q: str | None = None,
        status: MemberStatus | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[Member], int]:
        clauses = self._filters(q=q, status=status)
        stmt = (
            select(Member)
            .where(*clauses)
            .order_by(Member.full_name, Member.id)
            .offset(offset)
            .limit(limit)
        )
        items = list((await self.session.execute(stmt)).scalars().all())
        return items, await self.count(*clauses)

    async def get_by_email(self, email: str) -> Member | None:
        stmt = select(Member).where(func.lower(Member.email) == email.strip().lower())
        return (await self.session.execute(stmt)).scalars().one_or_none()

    async def open_loan_count(self, member_id: int) -> int:
        stmt = (
            select(func.count())
            .select_from(Loan)
            .where(Loan.member_id == member_id, Loan.returned_at.is_(None))
        )
        return (await self.session.execute(stmt)).scalar_one()

    async def total_loan_count(self, member_id: int) -> int:
        stmt = select(func.count()).select_from(Loan).where(Loan.member_id == member_id)
        return (await self.session.execute(stmt)).scalar_one()
