"""Health, statistics and application metadata tests."""

from __future__ import annotations

from tests.conftest import API


async def test_root_banner(client):
    response = await client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["api"] == API
    assert body["docs"] == "/docs"


async def test_health_reports_database_reachable(client):
    response = await client.get(f"{API}/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "reachable"


async def test_stats_reflect_library_activity(client, make_book, make_member):
    empty = (await client.get(f"{API}/stats")).json()
    assert empty["total_books"] == 0
    assert empty["open_loans"] == 0

    book = await make_book(total_copies=3)
    member = await make_member()
    loan = await client.post(
        f"{API}/loans", json={"book_id": book["id"], "member_id": member["id"]}
    )
    await client.post(f"{API}/loans/{loan.json()['id']}/return")

    filled = (await client.get(f"{API}/stats")).json()
    assert filled["total_books"] == 1
    assert filled["total_copies"] == 3
    assert filled["available_copies"] == 3
    assert filled["total_members"] == 1
    assert filled["active_members"] == 1
    assert filled["open_loans"] == 0
    assert filled["overdue_loans"] == 0
    assert filled["completed_loans"] == 1


async def test_stats_count_open_and_overdue_loans(client, make_book, make_member, age_loan):
    book = await make_book(total_copies=2)
    first = await make_member(email="first@example.com")
    second = await make_member(email="second@example.com")

    overdue_loan = (
        await client.post(f"{API}/loans", json={"book_id": book["id"], "member_id": first["id"]})
    ).json()
    await client.post(f"{API}/loans", json={"book_id": book["id"], "member_id": second["id"]})
    await age_loan(overdue_loan["id"], overdue_by_days=5)

    stats = (await client.get(f"{API}/stats")).json()
    assert stats["open_loans"] == 2
    assert stats["overdue_loans"] == 1


async def test_openapi_describes_every_resource(client):
    response = await client.get(f"{API}/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    for path in (
        "/api/v1/authors",
        "/api/v1/books",
        "/api/v1/members",
        "/api/v1/loans",
        "/api/v1/loans/{loan_id}/return",
        "/api/v1/stats",
    ):
        assert path in paths
