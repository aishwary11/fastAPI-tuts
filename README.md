# Library API

A library management REST API built with **FastAPI**, **SQLAlchemy 2.0 (async ORM)** and
**PostgreSQL**. It tracks a catalogue of authors and books, its members, and the loans
between them.

Stack choices, briefly:

| Concern | Choice | Why |
| --- | --- | --- |
| ORM | SQLAlchemy 2.0 async ORM | The mature, typed ORM for Python; async support is first-class and works with FastAPI's async endpoints. |
| Driver | `asyncpg` | Fastest PostgreSQL driver for asyncio. |
| Migrations | Alembic (async) | The official SQLAlchemy migration tool, so the schema has one source of truth. |
| Validation | Pydantic v2 + pydantic-settings | FastAPI's native validation; settings come from the environment. |
| Tests | pytest + pytest-asyncio + httpx | Tests run against a real PostgreSQL database built from the real migrations. |

## Features

- **Catalogue** — authors and books, with a per-copy availability counter.
- **Members** — registration, membership status (`active` / `suspended` / `inactive`).
- **Circulation** — borrow, return and renew, with `overdue` reporting.
- Pagination, search and filtering on every collection endpoint.
- **Middleware** — request ids, timing headers, CORS and a per-client rate limit.
- Interactive docs at `/docs` (ReDoc at `/redoc`).

## Quick start

```bash
# 1. Create a virtualenv with any Python 3.11+ interpreter and install deps.
#    Depending on your setup that interpreter may be `python`, `py -3.14`, or
#    its full path (on Windows the Store alias leaves bare `python` unusable).
python -m venv .venv

.venv/Scripts/python.exe -m pip install -e ".[dev]"     # Windows
# source .venv/bin/activate && pip install -e ".[dev]"  # macOS / Linux

# 2. Configure the database
cp .env.example .env        # then edit POSTGRES_* to match your server
createdb -U postgres library

# 3. Create the schema and load sample data
python -m alembic upgrade head
python -m scripts.seed

# 4. Run it
python -m uvicorn app.main:app --reload
```

Then open <http://127.0.0.1:8000/docs>.

## Configuration

Settings are read from environment variables, falling back to `.env`
(see [`.env.example`](.env.example)). Either set the individual `POSTGRES_*`
values, or set `DATABASE_URL` to a complete SQLAlchemy URL.

| Variable | Default | Purpose |
| --- | --- | --- |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_HOST` / `POSTGRES_PORT` / `POSTGRES_DB` | `postgres` / – / `localhost` / `5432` / `library` | Connection parts. |
| `DATABASE_URL` | – | Full URL; overrides the parts above. |
| `LOAN_PERIOD_DAYS` | `14` | Loan length, also the renewal length. |
| `MAX_ACTIVE_LOANS_PER_MEMBER` | `5` | Cap on simultaneously open loans per member. |
| `DB_ECHO` | `false` | Log every SQL statement. |
| `CORS_ALLOW_ORIGINS` | `*` | Comma-separated allowed origins. |
| `RATE_LIMIT_ENABLED` | `true` | Turn the limiter off entirely. |
| `RATE_LIMIT_REQUESTS` | `10` | Requests allowed per client per window. |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | Length of the sliding window. |
| `TRUST_PROXY_HEADERS` | `false` | Trust client `X-Forwarded-For` (only behind a proxy you control). |

## API

All endpoints are under `/api/v1`. Collections return a page envelope:
`{ items, total, limit, offset }` with `limit` (1–100) and `offset` query parameters.

### Authors

| Method | Path | Notes |
| --- | --- | --- |
| `GET` | `/authors` | `?q=` filters by name. |
| `POST` | `/authors` | |
| `GET` | `/authors/{id}` | Includes the author's books. |
| `PATCH` | `/authors/{id}` | Partial update. |
| `DELETE` | `/authors/{id}` | `409` while the author still has books. |

### Books

| Method | Path | Notes |
| --- | --- | --- |
| `GET` | `/books` | `?q=` searches title, ISBN and author name; also `?author_id=`, `?genre=`, `?available_only=`. |
| `GET` | `/books/genres` | Distinct genres in use. |
| `POST` | `/books` | ISBN separators are stripped; duplicates return `409`. |
| `GET` | `/books/{id}` | |
| `PATCH` | `/books/{id}` | Changing `total_copies` keeps borrowed copies consistent. |
| `DELETE` | `/books/{id}` | `409` once the book has loan history. |

### Members

| Method | Path | Notes |
| --- | --- | --- |
| `GET` | `/members` | `?q=` searches name/email; `?status=`. |
| `POST` | `/members` | Emails are unique and stored lowercased. |
| `GET` | `/members/{id}` | |
| `GET` | `/members/{id}/loans` | Borrowing history; `?status=active\|overdue\|returned`. |
| `PATCH` | `/members/{id}` | |
| `DELETE` | `/members/{id}` | `409` with any loan history — use `status: inactive` instead. |

### Loans

| Method | Path | Notes |
| --- | --- | --- |
| `GET` | `/loans` | `?status=`, `?member_id=`, `?book_id=`. |
| `GET` | `/loans/overdue` | Everything past its due date. |
| `POST` | `/loans` | Borrow `{ book_id, member_id }`. |
| `GET` | `/loans/{id}` | |
| `POST` | `/loans/{id}/return` | Returns the copy to the shelf. |
| `POST` | `/loans/{id}/renew` | Extends by one loan period; overdue loans are refused. |

### System

| Method | Path | Notes |
| --- | --- | --- |
| `GET` | `/health` | Pings the database; `503` when unreachable. |
| `GET` | `/stats` | Library-wide aggregates. |

Loan `status` (`active` / `overdue` / `returned`) is **derived** from
`returned_at` and `due_at` — it is never stored, so it cannot drift.

### Example

```bash
BASE=http://127.0.0.1:8000/api/v1

curl -s -X POST $BASE/authors -H 'content-type: application/json' \
  -d '{"name":"Ursula K. Le Guin","country":"United States"}'

curl -s -X POST $BASE/books -H 'content-type: application/json' \
  -d '{"title":"A Wizard of Earthsea","author_id":1,"total_copies":2}'

curl -s -X POST $BASE/members -H 'content-type: application/json' \
  -d '{"full_name":"Ada Lovelace","email":"ada@example.com"}'

curl -s -X POST $BASE/loans -H 'content-type: application/json' \
  -d '{"book_id":1,"member_id":1}'

curl -s -X POST $BASE/loans/1/return
curl -s $BASE/stats
```

## Middleware

Three layers wrap every request, applied outermost-first:

```
RequestContext  ->  RateLimit  ->  CORS  ->  routes
```

### Request context — `app/middleware.py`

- honours an inbound `X-Request-ID` so an id survives across services, and
  generates one otherwise (values over 128 characters are replaced);
- returns it as `X-Request-ID` and adds `X-Process-Time-Ms`;
- stores it in a `ContextVar`, which is why error bodies carry the same
  `request_id` as the header — a client can quote it when reporting a failure.

It is raw ASGI middleware rather than `BaseHTTPMiddleware`, so it costs no extra
task per request and cannot break streaming responses.

### Rate limiting — `app/rate_limit.py`

A sliding-window limiter keyed by client address: **10 requests per 60 seconds**
by default. Sliding rather than fixed, so a client cannot burst 20 requests in
the second that straddles two windows.

```console
$ curl -s -D - -o /dev/null http://127.0.0.1:8000/api/v1/stats
x-ratelimit-limit: 10
x-ratelimit-remaining: 9
x-ratelimit-reset: 60

# 11th request inside the window
HTTP/1.1 429 Too Many Requests
retry-after: 60

{"detail": "Rate limit exceeded: 10 requests per 60s. Retry in 60s.",
 "code": "rate_limited"}
```

`/`, `/docs`, `/redoc`, `/openapi.json` and `/api/v1/health` are exempt, so
monitoring and the docs keep working while a client is being throttled.
`OPTIONS` preflights are exempt too — otherwise CORS would break under load.

> **Scaling note.** Counters live in this process. With several workers or
> containers each keeps its own window, so the effective limit becomes
> `RATE_LIMIT_REQUESTS × workers`. Put the limiter behind Redis if you need a
> hard global limit.

`X-Forwarded-For` is ignored unless `TRUST_PROXY_HEADERS=true`: otherwise any
client could present a fresh identity on every request and never be limited.
Only enable it behind a proxy you control.

Clicking around `/docs` will trip a 10/minute limit quickly. Raise
`RATE_LIMIT_REQUESTS` or set `RATE_LIMIT_ENABLED=false` while developing.

### CORS — `fastapi.middleware.cors`

Enabled for the origins in `CORS_ALLOW_ORIGINS`. Credentials stay disabled — the
API needs no cookies, and browsers reject `allow_credentials` combined with a
`*` origin anyway. `X-Request-ID` and `X-Process-Time-Ms` are exposed so browser
clients can read them.

## Architecture

```
app/
├── config.py          # pydantic-settings, URL assembly
├── database.py        # async engine, session factory, get_session dependency
├── exceptions.py      # domain errors -> HTTP status codes
├── middleware.py      # request ids, timing, access log, CORS options
├── rate_limit.py      # sliding-window limiter + its ASGI middleware
├── models/            # SQLAlchemy 2.0 ORM (Mapped[...] typed)
├── schemas/           # Pydantic request/response models
├── repositories/      # every SQL query lives here
├── services/          # business rules, expressed via repositories
├── api/v1/            # routers, one module per resource
└── main.py            # app factory, middleware stack, exception handlers
```

Middleware wraps everything; inside it, requests flow
**router → service → repository → database**. Routers stay thin; anything that
enforces a rule lives in `services/`.

### Invariants worth knowing

These are enforced in the database, not just in Python:

- `loans` has a **partial unique index** on `(book_id, member_id) WHERE returned_at IS NULL`,
  so a member cannot hold two open loans of the same book even if two requests race.
- `CHECK` constraints keep `0 <= available_copies <= total_copies` and `total_copies > 0`.
- Foreign keys are `ON DELETE RESTRICT`, which is why deleting an author or book with
  history returns `409` rather than silently orphaning rows.

Borrowing locks the book row (`SELECT ... FOR UPDATE`) before checking availability and
decrements the counter in the same transaction that inserts the loan, so concurrent
borrows serialise instead of overselling the last copy.

## Migrations

```bash
alembic upgrade head                            # apply
alembic downgrade base                          # roll back everything
alembic revision --autogenerate -m "message"    # create a new revision
```

`alembic/env.py` reads the database URL from `app.config`, so migrations always target
the same database as the application. Credentials are never stored in `alembic.ini`.

## Tests

```bash
python -m pytest -q        # 65 tests
ruff check .               # lint
ruff format --check .      # formatting
```

The suite covers the catalogue, circulation rules, error handling and the
middleware stack (including a test that drives the real 10-per-minute limit and
asserts the 11th request is rejected).

It runs against a real PostgreSQL database named `library_test`:

```bash
createdb -U postgres library_test
```

It rebuilds that schema from the Alembic migrations (not `create_all`), so a migration
that drifts from the models fails the suite. Each test starts with empty tables.
