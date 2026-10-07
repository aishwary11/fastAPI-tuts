"""Seed the database with a small, realistic library.

Run with::

    python -m scripts.seed            # skip if the catalogue is not empty
    python -m scripts.seed --reset    # wipe the library tables first

Loans are created through the real service layer, so the on-shelf counters and
the loan rows are guaranteed to be consistent.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, text

from app.database import SessionFactory, dispose_engine
from app.models import Book
from app.schemas.author import AuthorCreate
from app.schemas.book import BookCreate
from app.schemas.loan import LoanCreate
from app.schemas.member import MemberCreate
from app.services import authors as author_service
from app.services import books as book_service
from app.services import circulation
from app.services import members as member_service
from app.services import stats as stats_service

AUTHORS: list[dict] = [
    {
        "name": "George Orwell",
        "country": "United Kingdom",
        "bio": "Novelist and essayist, best known for dystopian fiction.",
    },
    {
        "name": "J.R.R. Tolkien",
        "country": "United Kingdom",
        "bio": "Philologist and author of the Middle-earth legendarium.",
    },
    {
        "name": "Jane Austen",
        "country": "United Kingdom",
        "bio": "Novelist of manners and marriage in Georgian England.",
    },
    {
        "name": "Isaac Asimov",
        "country": "United States",
        "bio": "Biochemist and prolific science-fiction author.",
    },
    {
        "name": "Ursula K. Le Guin",
        "country": "United States",
        "bio": "Author of the Earthsea and Hainish cycles.",
    },
]

BOOKS: list[dict] = [
    {
        "title": "1984",
        "author": "George Orwell",
        "isbn": "9780451524935",
        "genre": "Dystopian",
        "published_year": 1949,
        "total_copies": 4,
    },
    {
        "title": "Animal Farm",
        "author": "George Orwell",
        "isbn": "9780452284241",
        "genre": "Satire",
        "published_year": 1945,
        "total_copies": 3,
    },
    {
        "title": "The Hobbit",
        "author": "J.R.R. Tolkien",
        "isbn": "9780547928227",
        "genre": "Fantasy",
        "published_year": 1937,
        "total_copies": 2,
    },
    {
        "title": "The Fellowship of the Ring",
        "author": "J.R.R. Tolkien",
        "isbn": "9780618346257",
        "genre": "Fantasy",
        "published_year": 1954,
        "total_copies": 2,
    },
    {
        "title": "Pride and Prejudice",
        "author": "Jane Austen",
        "isbn": "9780141439518",
        "genre": "Classic",
        "published_year": 1813,
        "total_copies": 3,
    },
    {
        "title": "Foundation",
        "author": "Isaac Asimov",
        "isbn": "9780553293357",
        "genre": "Science Fiction",
        "published_year": 1951,
        "total_copies": 2,
    },
    {
        "title": "I, Robot",
        "author": "Isaac Asimov",
        "isbn": "9780553294385",
        "genre": "Science Fiction",
        "published_year": 1950,
        "total_copies": 1,
    },
    {
        "title": "The Left Hand of Darkness",
        "author": "Ursula K. Le Guin",
        "isbn": "9780441478125",
        "genre": "Science Fiction",
        "published_year": 1969,
        "total_copies": 2,
    },
    {
        "title": "A Wizard of Earthsea",
        "author": "Ursula K. Le Guin",
        "isbn": "9780553383041",
        "genre": "Fantasy",
        "published_year": 1968,
        "total_copies": 1,
    },
]

MEMBERS: list[dict] = [
    {"full_name": "Ada Lovelace", "email": "ada@example.com", "phone": "+44 20 7946 0001"},
    {"full_name": "Alan Turing", "email": "alan@example.com", "phone": "+44 20 7946 0002"},
    {"full_name": "Grace Hopper", "email": "grace@example.com", "phone": "+1 202 555 0143"},
    {
        "full_name": "Katherine Johnson",
        "email": "katherine@example.com",
        "phone": "+1 202 555 0177",
    },
    {
        "full_name": "Margaret Hamilton",
        "email": "margaret@example.com",
        "phone": "+1 617 555 0110",
    },
]

# (member index, book title) -- borrowed in order through the service layer.
BORROW_PLAN: list[tuple[int, str]] = [
    (0, "1984"),
    (1, "The Hobbit"),
    (2, "Pride and Prejudice"),
    (3, "Foundation"),
    (0, "Animal Farm"),
]


async def seed(reset: bool = False) -> None:
    async with SessionFactory() as session:
        if reset:
            await session.execute(
                text("TRUNCATE loans, books, members, authors RESTART IDENTITY CASCADE")
            )
            await session.commit()
            print("Existing library data removed.")
        else:
            existing = await session.scalar(select(func.count()).select_from(Book))
            if existing:
                print(
                    f"Catalogue already has {existing} book(s); nothing to do. "
                    "Re-run with --reset to replace the data."
                )
                return

        authors = {}
        for spec in AUTHORS:
            author = await author_service.create_author(session, AuthorCreate(**spec))
            authors[author.name] = author
        print(f"Created {len(authors)} authors.")

        books = {}
        for spec in BOOKS:
            payload = dict(spec)
            author_name = payload.pop("author")
            book = await book_service.create_book(
                session, BookCreate(author_id=authors[author_name].id, **payload)
            )
            books[book.title] = book
        print(f"Created {len(books)} books.")

        members = [
            await member_service.create_member(session, MemberCreate(**spec)) for spec in MEMBERS
        ]
        print(f"Created {len(members)} members.")

        loans = []
        for member_index, title in BORROW_PLAN:
            loan = await circulation.borrow_book(
                session,
                LoanCreate(book_id=books[title].id, member_id=members[member_index].id),
            )
            loans.append(loan)
        print(f"Created {len(loans)} loans.")

        # Return the last one so both open and completed loans are represented.
        await circulation.return_book(session, loans[-1].id)

        # Backdate the first loan so the overdue workflow has data to work with.
        now = datetime.now(UTC)
        await session.execute(
            text("UPDATE loans SET borrowed_at = :b, due_at = :d WHERE id = :i"),
            {
                "b": now - timedelta(days=21),
                "d": now - timedelta(days=7),
                "i": loans[0].id,
            },
        )
        await session.commit()

        summary = await stats_service.library_stats(session)
        print("\nLibrary seeded:")
        print(summary.model_dump_json(indent=2))


async def _run(reset: bool) -> None:
    try:
        await seed(reset=reset)
    finally:
        # Dispose inside the same event loop that opened the connections.
        await dispose_engine()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the library database.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete existing library data before seeding",
    )
    args = parser.parse_args()
    asyncio.run(_run(reset=args.reset))


if __name__ == "__main__":
    main()
