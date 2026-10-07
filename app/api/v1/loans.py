"""Loan endpoints: borrowing, returning, renewing."""

from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi import status as http

from app.api.deps import PageDep, SessionDep
from app.models import LoanStatus
from app.schemas.common import Page
from app.schemas.loan import LoanCreate, LoanRead
from app.services import circulation as service

router = APIRouter(prefix="/loans", tags=["loans"])


@router.get("", response_model=Page[LoanRead], summary="List loans")
async def list_loans(
    session: SessionDep,
    page: PageDep,
    loan_status: LoanStatus | None = Query(
        default=None, alias="status", description="Filter by derived loan status"
    ),
    member_id: int | None = Query(default=None, gt=0),
    book_id: int | None = Query(default=None, gt=0),
):
    items, total = await service.list_loans(
        session,
        status=loan_status,
        member_id=member_id,
        book_id=book_id,
        offset=page.offset,
        limit=page.limit,
    )
    return Page(items=items, total=total, limit=page.limit, offset=page.offset)


@router.get(
    "/overdue",
    response_model=Page[LoanRead],
    summary="Loans past their due date",
)
async def list_overdue(session: SessionDep, page: PageDep):
    items, total = await service.list_loans(
        session,
        status=LoanStatus.OVERDUE,
        offset=page.offset,
        limit=page.limit,
    )
    return Page(items=items, total=total, limit=page.limit, offset=page.offset)


@router.post(
    "",
    response_model=LoanRead,
    status_code=http.HTTP_201_CREATED,
    summary="Borrow a book",
)
async def borrow_book(session: SessionDep, payload: LoanCreate):
    return await service.borrow_book(session, payload)


@router.get("/{loan_id}", response_model=LoanRead, summary="Get a loan")
async def get_loan(session: SessionDep, loan_id: int):
    return await service.get_loan(session, loan_id)


@router.post("/{loan_id}/return", response_model=LoanRead, summary="Return a book")
async def return_book(session: SessionDep, loan_id: int):
    return await service.return_book(session, loan_id)


@router.post("/{loan_id}/renew", response_model=LoanRead, summary="Renew a loan")
async def renew_loan(session: SessionDep, loan_id: int):
    return await service.renew_loan(session, loan_id)
