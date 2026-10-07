"""Book endpoint tests, focused on the catalogue rules."""

from __future__ import annotations

from tests.conftest import API


async def test_create_book_starts_fully_available(client, make_author):
    author = await make_author()

    response = await client.post(
        f"{API}/books",
        json={"title": "1984", "author_id": author["id"], "total_copies": 3},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["total_copies"] == 3
    assert body["available_copies"] == 3
    assert body["is_available"] is True
    assert body["author"]["name"] == author["name"]


async def test_create_book_with_unknown_author_is_rejected(client):
    response = await client.post(f"{API}/books", json={"title": "Ghost", "author_id": 4242})
    assert response.status_code == 422
    assert "does not exist" in response.json()["detail"]


async def test_create_book_rejects_out_of_range_copies(client, make_author):
    author = await make_author()
    response = await client.post(
        f"{API}/books",
        json={"title": "Nope", "author_id": author["id"], "total_copies": 0},
    )
    assert response.status_code == 422


async def test_duplicate_isbn_conflicts(client, make_author, make_book):
    author = await make_author()
    await make_book(author_id=author["id"], isbn="9780451524935")

    response = await client.post(
        f"{API}/books",
        json={"title": "Copycat", "author_id": author["id"], "isbn": "9780451524935"},
    )
    assert response.status_code == 409
    assert "isbn" in response.json()["detail"].lower()


async def test_isbn_separators_are_stripped(client, make_book):
    book = await make_book(isbn="978-0-451-52493-5")
    assert book["isbn"] == "9780451524935"


async def test_invalid_isbn_is_rejected(client, make_author):
    author = await make_author()
    response = await client.post(
        f"{API}/books",
        json={"title": "Bad ISBN", "author_id": author["id"], "isbn": "not-an-isbn"},
    )
    assert response.status_code == 422


async def test_search_matches_title_isbn_and_author(client, make_author, make_book):
    tolkien = await make_author(name="J.R.R. Tolkien")
    orwell = await make_author(name="George Orwell")
    await make_book(author_id=tolkien["id"], title="The Hobbit", isbn="9780547928227")
    await make_book(author_id=orwell["id"], title="1984", isbn="9780451524935")

    by_title = await client.get(f"{API}/books", params={"q": "hobbit"})
    assert [b["title"] for b in by_title.json()["items"]] == ["The Hobbit"]

    by_author = await client.get(f"{API}/books", params={"q": "orwell"})
    assert [b["title"] for b in by_author.json()["items"]] == ["1984"]

    by_isbn = await client.get(f"{API}/books", params={"q": "9780547928227"})
    assert [b["title"] for b in by_isbn.json()["items"]] == ["The Hobbit"]


async def test_filter_by_author_and_genre(client, make_author, make_book):
    tolkien = await make_author(name="J.R.R. Tolkien")
    orwell = await make_author(name="George Orwell")
    await make_book(author_id=tolkien["id"], title="The Hobbit", genre="Fantasy")
    await make_book(author_id=orwell["id"], title="1984", genre="Dystopian")

    by_author = await client.get(f"{API}/books", params={"author_id": tolkien["id"]})
    assert [b["title"] for b in by_author.json()["items"]] == ["The Hobbit"]

    by_genre = await client.get(f"{API}/books", params={"genre": "Dystopian"})
    assert [b["title"] for b in by_genre.json()["items"]] == ["1984"]

    genres = await client.get(f"{API}/books/genres")
    assert genres.json() == ["Dystopian", "Fantasy"]


async def test_available_only_hides_fully_borrowed_books(client, make_book, make_member):
    book = await make_book(total_copies=1)
    member = await make_member()
    await client.post(f"{API}/loans", json={"book_id": book["id"], "member_id": member["id"]})

    all_books = await client.get(f"{API}/books")
    assert all_books.json()["total"] == 1

    available = await client.get(f"{API}/books", params={"available_only": True})
    body = available.json()
    assert body["total"] == 0
    assert body["items"] == []


async def test_cannot_shrink_total_below_copies_on_loan(client, make_book, make_member):
    book = await make_book(total_copies=3)
    first = await make_member(email="first@example.com")
    second = await make_member(email="second@example.com")
    for member in (first, second):
        loan = await client.post(
            f"{API}/loans", json={"book_id": book["id"], "member_id": member["id"]}
        )
        assert loan.status_code == 201

    response = await client.patch(f"{API}/books/{book['id']}", json={"total_copies": 1})
    assert response.status_code == 422
    assert "on loan" in response.json()["detail"]


async def test_growing_total_copies_keeps_borrowed_copies_checked_out(
    client, make_book, make_member
):
    book = await make_book(total_copies=3)
    first = await make_member(email="first@example.com")
    second = await make_member(email="second@example.com")
    for member in (first, second):
        await client.post(f"{API}/loans", json={"book_id": book["id"], "member_id": member["id"]})

    response = await client.patch(f"{API}/books/{book['id']}", json={"total_copies": 5})
    assert response.status_code == 200
    body = response.json()
    assert body["total_copies"] == 5
    # 5 on the shelf, 2 already out.
    assert body["available_copies"] == 3


async def test_delete_book_with_loan_history_conflicts(client, make_book, make_member):
    book = await make_book()
    member = await make_member()
    loan = await client.post(
        f"{API}/loans", json={"book_id": book["id"], "member_id": member["id"]}
    )
    await client.post(f"{API}/loans/{loan.json()['id']}/return")

    response = await client.delete(f"{API}/books/{book['id']}")
    assert response.status_code == 409
    assert (await client.get(f"{API}/books/{book['id']}")).status_code == 200


async def test_delete_book_without_loans(client, make_book):
    book = await make_book()
    response = await client.delete(f"{API}/books/{book['id']}")
    assert response.status_code == 200
    assert (await client.get(f"{API}/books/{book['id']}")).status_code == 404


async def test_missing_book_returns_404(client):
    response = await client.get(f"{API}/books/9999")
    assert response.status_code == 404
