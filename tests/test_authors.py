"""Author endpoint tests."""

from __future__ import annotations

from tests.conftest import API


async def test_create_and_fetch_author(client):
    response = await client.post(
        f"{API}/authors",
        json={"name": "Isaac Asimov", "country": "United States", "bio": "Prolific."},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Isaac Asimov"
    assert body["id"] > 0
    assert body["created_at"] and body["updated_at"]

    fetched = await client.get(f"{API}/authors/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["books"] == []


async def test_create_author_rejects_blank_name(client):
    response = await client.post(f"{API}/authors", json={"name": ""})
    assert response.status_code == 422


async def test_list_authors_paginates(client, make_author):
    for index in range(3):
        await make_author(name=f"Author {index}")

    first = await client.get(f"{API}/authors", params={"limit": 2, "offset": 0})
    assert first.status_code == 200
    body = first.json()
    assert body["total"] == 3
    assert body["limit"] == 2
    assert body["offset"] == 0
    assert len(body["items"]) == 2

    second = await client.get(f"{API}/authors", params={"limit": 2, "offset": 2})
    assert len(second.json()["items"]) == 1


async def test_list_authors_filters_by_name(client, make_author):
    await make_author(name="Jane Austen")
    await make_author(name="Isaac Asimov")

    response = await client.get(f"{API}/authors", params={"q": "asimov"})
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["name"] == "Isaac Asimov"


async def test_author_detail_includes_their_books(client, make_author, make_book):
    author = await make_author(name="J.R.R. Tolkien")
    await make_book(author_id=author["id"], title="The Hobbit")
    await make_book(author_id=author["id"], title="The Fellowship of the Ring")

    response = await client.get(f"{API}/authors/{author['id']}")
    assert response.status_code == 200
    titles = {book["title"] for book in response.json()["books"]}
    assert titles == {"The Hobbit", "The Fellowship of the Ring"}


async def test_patch_author_only_touches_supplied_fields(client, make_author):
    author = await make_author(name="Jane Austen", country="United Kingdom", bio="Novelist")

    response = await client.patch(f"{API}/authors/{author['id']}", json={"country": "England"})
    assert response.status_code == 200
    body = response.json()
    assert body["country"] == "England"
    assert body["name"] == "Jane Austen"
    assert body["bio"] == "Novelist"


async def test_delete_author_without_books(client, make_author):
    author = await make_author()

    response = await client.delete(f"{API}/authors/{author['id']}")
    assert response.status_code == 200
    assert (await client.get(f"{API}/authors/{author['id']}")).status_code == 404


async def test_delete_author_with_books_conflicts(client, make_author, make_book):
    author = await make_author()
    await make_book(author_id=author["id"])

    response = await client.delete(f"{API}/authors/{author['id']}")
    assert response.status_code == 409
    assert "book" in response.json()["detail"].lower()
    # The author survives the rejected delete.
    assert (await client.get(f"{API}/authors/{author['id']}")).status_code == 200


async def test_missing_author_returns_404(client):
    response = await client.get(f"{API}/authors/9999")
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"
