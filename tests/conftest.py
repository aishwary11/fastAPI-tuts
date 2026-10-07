"""Shared test fixtures.

The suite runs against a real PostgreSQL database (``library_test``) whose schema
is built by running the actual Alembic migrations -- so the tests exercise the
same DDL that production uses, not a ``create_all`` approximation.

The environment must be redirected to the test database *before* ``app.config``
is imported anywhere, hence the assignments at the very top of this module.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import AsyncIterator, Iterator

os.environ["POSTGRES_DB"] = "library_test"
os.environ["ENVIRONMENT"] = "test"
os.environ["DB_ECHO"] = "false"
# The functional suite makes far more than 10 requests per test; the rate
# limiter gets its own dedicated tests that lower this back to a real budget.
os.environ["RATE_LIMIT_DEFAULT"] = "100000/minute"

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.database import engine  # noqa: E402
from app.main import app  # noqa: E402

API = "/api/v1"
TRUNCATE_TABLES = "loans, books, members, authors"


def _alembic(*args: str) -> subprocess.CompletedProcess[str]:
    """Run the Alembic CLI in a subprocess against the test database."""
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        capture_output=True,
        text=True,
        env={**os.environ, "POSTGRES_DB": "library_test", "ENVIRONMENT": "test"},
        check=False,
    )


@pytest.fixture(scope="session", autouse=True)
def migrated_database() -> Iterator[None]:
    """Rebuild the test schema from scratch using the real migrations."""
    _alembic("downgrade", "base")
    result = _alembic("upgrade", "head")
    assert result.returncode == 0, f"alembic upgrade failed:\n{result.stderr}"
    yield


@pytest_asyncio.fixture(autouse=True)
async def clean_tables() -> AsyncIterator[None]:
    """Give every test an empty library and a fresh rate-limit window."""
    async with engine.begin() as connection:
        await connection.execute(text(f"TRUNCATE {TRUNCATE_TABLES} RESTART IDENTITY CASCADE"))
    app.state.limiter.reset()
    yield


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


@pytest_asyncio.fixture
async def age_loan():
    """Backdate a loan so overdue behaviour can be exercised."""
    from datetime import UTC, datetime, timedelta

    async def _age(loan_id: int, *, overdue_by_days: int) -> None:
        due = datetime.now(UTC) - timedelta(days=overdue_by_days)
        async with engine.begin() as connection:
            await connection.execute(
                text("UPDATE loans SET borrowed_at = :borrowed, due_at = :due WHERE id = :id"),
                {"borrowed": due - timedelta(days=14), "due": due, "id": loan_id},
            )

    return _age


# --------------------------------------------------------------------------
# Object factories -- each posts through the real API.
# --------------------------------------------------------------------------


@pytest.fixture
def make_author(client: AsyncClient):
    async def _make(**overrides: object) -> dict:
        payload = {"name": "Ursula K. Le Guin", "country": "United States"} | overrides
        response = await client.post(f"{API}/authors", json=payload)
        assert response.status_code == 201, response.text
        return response.json()

    return _make


@pytest.fixture
def make_book(client: AsyncClient, make_author):
    async def _make(*, author_id: int | None = None, **overrides: object) -> dict:
        if author_id is None:
            author_id = (await make_author())["id"]
        payload = {"title": "The Left Hand of Darkness", "author_id": author_id} | overrides
        response = await client.post(f"{API}/books", json=payload)
        assert response.status_code == 201, response.text
        return response.json()

    return _make


@pytest.fixture
def make_member(client: AsyncClient):
    async def _make(**overrides: object) -> dict:
        payload = {"full_name": "Ada Lovelace", "email": "ada@example.com"} | overrides
        response = await client.post(f"{API}/members", json=payload)
        assert response.status_code == 201, response.text
        return response.json()

    return _make
