"""Circulation tests: the rules that protect the library's invariants."""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.database import SessionFactory
from tests.conftest import API


async def _borrow(client, book: dict, member: dict):
    return await client.post(
        f"{API}/loans", json={"book_id": book["id"], "member_id": member["id"]}
    )


async def test_borrow_decrements_available_copies(client, make_book, make_member):
    book = await make_book(total_copies=2)
    member = await make_member()

    response = await _borrow(client, book, member)
    assert response.status_code == 201
    loan = response.json()
    assert loan["status"] == "active"
    assert loan["returned_at"] is None
    assert loan["book"]["title"] == book["title"]
    assert loan["member"]["email"] == member["email"]

    after = (await client.get(f"{API}/books/{book['id']}")).json()
    assert after["available_copies"] == 1
    assert after["total_copies"] == 2


async def test_borrowing_the_last_copy_marks_book_unavailable(client, make_book, make_member):
    book = await make_book(total_copies=1)
    member = await make_member()

    assert (await _borrow(client, book, member)).status_code == 201

    after = (await client.get(f"{API}/books/{book['id']}")).json()
    assert after["available_copies"] == 0
    assert after["is_available"] is False

    other = await make_member(email="other@example.com")
    blocked = await _borrow(client, book, other)
    assert blocked.status_code == 409
    assert "no copies available" in blocked.json()["detail"]


async def test_member_cannot_hold_two_open_loans_of_same_book(client, make_book, make_member):
    book = await make_book(total_copies=2)
    member = await make_member()
    assert (await _borrow(client, book, member)).status_code == 201

    duplicate = await _borrow(client, book, member)
    assert duplicate.status_code == 409
    assert "already has an open loan" in duplicate.json()["detail"]

    # Only one copy was taken.
    after = (await client.get(f"{API}/books/{book['id']}")).json()
    assert after["available_copies"] == 1


async def test_suspended_member_cannot_borrow(client, make_book, make_member):
    book = await make_book()
    member = await make_member()
    await client.patch(f"{API}/members/{member['id']}", json={"status": "suspended"})

    response = await _borrow(client, book, member)
    assert response.status_code == 422
    assert "cannot borrow" in response.json()["detail"]


async def test_active_loan_limit_is_enforced(client, make_author, make_book, make_member):
    author = await make_author()
    member = await make_member()

    for index in range(5):
        book = await make_book(author_id=author["id"], title=f"Book {index}")
        assert (await _borrow(client, book, member)).status_code == 201

    sixth = await make_book(author_id=author["id"], title="Book 6")
    response = await _borrow(client, sixth, member)
    assert response.status_code == 422
    assert "limit is 5" in response.json()["detail"]


async def test_return_restores_availability(client, make_book, make_member):
    book = await make_book(total_copies=1)
    member = await make_member()
    loan = (await _borrow(client, book, member)).json()

    response = await client.post(f"{API}/loans/{loan['id']}/return")
    assert response.status_code == 200
    returned = response.json()
    assert returned["returned_at"] is not None
    assert returned["status"] == "returned"

    after = (await client.get(f"{API}/books/{book['id']}")).json()
    assert after["available_copies"] == 1

    # The member may now borrow the same book again.
    assert (await _borrow(client, book, member)).status_code == 201


async def test_returning_twice_conflicts(client, make_book, make_member):
    book = await make_book()
    member = await make_member()
    loan = (await _borrow(client, book, member)).json()
    await client.post(f"{API}/loans/{loan['id']}/return")

    response = await client.post(f"{API}/loans/{loan['id']}/return")
    assert response.status_code == 409
    assert "already returned" in response.json()["detail"]


async def test_renew_extends_the_due_date(client, make_book, make_member):
    book = await make_book()
    member = await make_member()
    loan = (await _borrow(client, book, member)).json()

    response = await client.post(f"{API}/loans/{loan['id']}/renew")
    assert response.status_code == 200
    renewed = response.json()
    assert datetime.fromisoformat(renewed["due_at"]) > datetime.fromisoformat(loan["due_at"])
    assert renewed["status"] == "active"


async def test_overdue_loans_cannot_be_renewed(client, make_book, make_member, age_loan):
    book = await make_book()
    member = await make_member()
    loan = (await _borrow(client, book, member)).json()
    await age_loan(loan["id"], overdue_by_days=3)

    response = await client.post(f"{API}/loans/{loan['id']}/renew")
    assert response.status_code == 409
    assert "overdue" in response.json()["detail"]


async def test_overdue_reporting_and_status_filter(client, make_book, make_member, age_loan):
    book = await make_book()
    member = await make_member()
    loan = (await _borrow(client, book, member)).json()
    await age_loan(loan["id"], overdue_by_days=2)

    overdue = await client.get(f"{API}/loans/overdue")
    assert overdue.status_code == 200
    body = overdue.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == loan["id"]
    assert body["items"][0]["status"] == "overdue"

    active = await client.get(f"{API}/loans", params={"status": "active"})
    assert active.json()["total"] == 0

    everything = await client.get(f"{API}/loans")
    assert everything.json()["total"] == 1


async def test_loans_can_be_filtered_by_book_and_member(client, make_book, make_member):
    first_book = await make_book(title="First")
    second_book = await make_book(title="Second")
    member = await make_member()
    other = await make_member(email="other@example.com")
    await _borrow(client, first_book, member)
    await _borrow(client, second_book, other)

    by_book = await client.get(f"{API}/loans", params={"book_id": first_book["id"]})
    assert by_book.json()["total"] == 1
    assert by_book.json()["items"][0]["book"]["title"] == "First"

    by_member = await client.get(f"{API}/loans", params={"member_id": other["id"]})
    assert by_member.json()["total"] == 1
    assert by_member.json()["items"][0]["member"]["email"] == "other@example.com"


async def test_borrow_unknown_book_or_member_returns_404(client, make_book, make_member):
    book = await make_book()
    member = await make_member()

    missing_book = await client.post(
        f"{API}/loans", json={"book_id": 9999, "member_id": member["id"]}
    )
    assert missing_book.status_code == 404
    assert "Book 9999 not found" in missing_book.json()["detail"]

    missing_member = await client.post(
        f"{API}/loans", json={"book_id": book["id"], "member_id": 9999}
    )
    assert missing_member.status_code == 404
    assert "Member 9999 not found" in missing_member.json()["detail"]


async def test_missing_loan_returns_404(client):
    assert (await client.get(f"{API}/loans/9999")).status_code == 404
    assert (await client.post(f"{API}/loans/9999/return")).status_code == 404


async def test_database_rejects_a_second_open_loan(client, make_book, make_member):
    """The partial unique index is the last line of defence, below the service."""
    book = await make_book(total_copies=2)
    member = await make_member()
    assert (await _borrow(client, book, member)).status_code == 201

    with pytest.raises(IntegrityError):
        async with SessionFactory() as session:
            await session.execute(
                text(
                    "INSERT INTO loans (book_id, member_id, borrowed_at, due_at) "
                    "VALUES (:book_id, :member_id, now(), now() + interval '14 days')"
                ),
                {"book_id": book["id"], "member_id": member["id"]},
            )
            await session.commit()
