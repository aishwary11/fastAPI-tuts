"""Member endpoint tests."""

from __future__ import annotations

from tests.conftest import API


async def test_register_member(client):
    response = await client.post(
        f"{API}/members",
        json={
            "full_name": "Grace Hopper",
            "email": "grace@example.com",
            "phone": "+1 202 555 0143",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["full_name"] == "Grace Hopper"
    assert body["status"] == "active"
    assert body["can_borrow"] is True


async def test_duplicate_email_conflicts(client, make_member):
    await make_member(email="ada@example.com")

    response = await client.post(
        f"{API}/members", json={"full_name": "Impostor", "email": "ada@example.com"}
    )
    assert response.status_code == 409
    assert "email" in response.json()["detail"].lower()


async def test_invalid_email_is_rejected(client):
    response = await client.post(
        f"{API}/members", json={"full_name": "Nobody", "email": "not-an-email"}
    )
    assert response.status_code == 422


async def test_email_is_normalised_to_lowercase(client):
    response = await client.post(
        f"{API}/members", json={"full_name": "Mixed Case", "email": "Mixed.Case@Example.COM"}
    )
    assert response.status_code == 201
    assert response.json()["email"] == "mixed.case@example.com"


async def test_filter_members_by_status(client, make_member):
    await make_member(email="active@example.com")
    suspended = await make_member(email="suspended@example.com")
    await client.patch(f"{API}/members/{suspended['id']}", json={"status": "suspended"})

    response = await client.get(f"{API}/members", params={"status": "suspended"})
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["email"] == "suspended@example.com"


async def test_search_members_by_name_or_email(client, make_member):
    await make_member(full_name="Ada Lovelace", email="ada@example.com")
    await make_member(full_name="Alan Turing", email="alan@example.com")

    by_name = await client.get(f"{API}/members", params={"q": "turing"})
    assert by_name.json()["total"] == 1

    by_email = await client.get(f"{API}/members", params={"q": "ada@"})
    assert by_email.json()["total"] == 1


async def test_member_loans_endpoint(client, make_book, make_member):
    book = await make_book()
    member = await make_member()
    loan = await client.post(
        f"{API}/loans", json={"book_id": book["id"], "member_id": member["id"]}
    )
    assert loan.status_code == 201

    response = await client.get(f"{API}/members/{member['id']}/loans")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["book"]["title"] == book["title"]

    open_only = await client.get(f"{API}/members/{member['id']}/loans", params={"status": "active"})
    assert open_only.json()["total"] == 1

    returned_only = await client.get(
        f"{API}/members/{member['id']}/loans", params={"status": "returned"}
    )
    assert returned_only.json()["total"] == 0


async def test_loans_for_missing_member_returns_404(client):
    response = await client.get(f"{API}/members/9999/loans")
    assert response.status_code == 404


async def test_delete_member_with_open_loan_conflicts(client, make_book, make_member):
    book = await make_book()
    member = await make_member()
    await client.post(f"{API}/loans", json={"book_id": book["id"], "member_id": member["id"]})

    response = await client.delete(f"{API}/members/{member['id']}")
    assert response.status_code == 409
    assert "on loan" in response.json()["detail"]


async def test_delete_member_with_history_suggests_deactivation(client, make_book, make_member):
    book = await make_book()
    member = await make_member()
    loan = await client.post(
        f"{API}/loans", json={"book_id": book["id"], "member_id": member["id"]}
    )
    await client.post(f"{API}/loans/{loan.json()['id']}/return")

    response = await client.delete(f"{API}/members/{member['id']}")
    assert response.status_code == 409
    assert "inactive" in response.json()["detail"]


async def test_delete_member_without_history(client, make_member):
    member = await make_member()
    response = await client.delete(f"{API}/members/{member['id']}")
    assert response.status_code == 200
    assert (await client.get(f"{API}/members/{member['id']}")).status_code == 404
