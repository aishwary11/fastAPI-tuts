"""Circulation: borrowing, returning and renewing books.

This is where the invariants of the library live. Two rules matter for
correctness under concurrency:

* the ``books`` row is locked with ``SELECT ... FOR UPDATE`` before the
  availability check, so two simultaneous borrows serialize;
* the open loan is created inside the same transaction as the counter
  decrement, so the counters can never drift from the loan table.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.exceptions import ConflictError, NotFoundError, ValidationError
from app.models import Book, Loan, LoanStatus, Member
from app.repositories import BookRepository, LoanRepository, MemberRepository
from app.schemas.loan import LoanCreate


def utcnow() -> datetime:
    return datetime.now(UTC)


async def list_loans(
    session: AsyncSession,
    *,
    status: LoanStatus | None = None,
    member_id: int | None = None,
    book_id: int | None = None,
    offset: int = 0,
    limit: int = 20,
) -> tuple[list[Loan], int]:
    return await LoanRepository(session).list(
        status=status,
        member_id=member_id,
        book_id=book_id,
        offset=offset,
        limit=limit,
    )


async def get_loan(session: AsyncSession, loan_id: int) -> Loan:
    loan = await LoanRepository(session).get(loan_id)
    if loan is None:
        raise NotFoundError(f"Loan {loan_id} not found")
    return loan


async def borrow_book(session: AsyncSession, payload: LoanCreate) -> Loan:
    """Check a copy of ``payload.book_id`` out to ``payload.member_id``."""
    members = MemberRepository(session)
    books = BookRepository(session)
    loans = LoanRepository(session)

    member: Member | None = await members.get(payload.member_id)
    if member is None:
        raise NotFoundError(f"Member {payload.member_id} not found")
    if not member.can_borrow:
        raise ValidationError(
            f"Member {member.id} has status '{member.status.value}' and cannot borrow books."
        )

    open_loans = await members.open_loan_count(member.id)
    if open_loans >= settings.max_active_loans_per_member:
        raise ValidationError(
            f"Member {member.id} already has {open_loans} open loan(s); "
            f"the limit is {settings.max_active_loans_per_member}."
        )

    # Lock the copy counter, then re-read the state we are validating.
    book: Book | None = await books.get(payload.book_id, for_update=True)
    if book is None:
        raise NotFoundError(f"Book {payload.book_id} not found")
    if book.available_copies <= 0:
        raise ConflictError(f"'{book.title}' has no copies available right now")

    if await loans.get_open_loan(book.id, member.id) is not None:
        raise ConflictError(f"Member {member.id} already has an open loan for '{book.title}'.")

    now = utcnow()
    loan = await loans.add(
        book_id=book.id,
        member_id=member.id,
        borrowed_at=now,
        due_at=now + timedelta(days=settings.loan_period_days),
    )
    book.available_copies -= 1
    await session.commit()
    await session.refresh(loan)
    return loan


async def return_book(session: AsyncSession, loan_id: int) -> Loan:
    """Mark a loan as returned and put the copy back on the shelf."""
    loans = LoanRepository(session)
    books = BookRepository(session)

    loan: Loan | None = await loans.get(loan_id, for_update=True)
    if loan is None:
        raise NotFoundError(f"Loan {loan_id} not found")
    if loan.returned_at is not None:
        raise ConflictError(f"Loan {loan_id} was already returned")

    book = await books.get(loan.book_id, for_update=True)
    if book is None:  # pragma: no cover - FK guarantees the book exists
        raise NotFoundError(f"Book {loan.book_id} not found")

    loan.returned_at = utcnow()
    # Clamp so a stray double-decrement can never exceed the shelf count.
    book.available_copies = min(book.total_copies, book.available_copies + 1)
    await session.commit()
    await session.refresh(loan)
    return loan


async def renew_loan(session: AsyncSession, loan_id: int) -> Loan:
    """Extend an active (not overdue) loan by one more loan period."""
    loan = await get_loan(session, loan_id)

    if loan.returned_at is not None:
        raise ConflictError(f"Loan {loan_id} was already returned")
    if loan.due_at < utcnow():
        raise ConflictError(
            f"Loan {loan_id} is overdue and must be returned before it can be renewed"
        )

    loan.due_at = loan.due_at + timedelta(days=settings.loan_period_days)
    await session.commit()
    await session.refresh(loan)
    return loan
