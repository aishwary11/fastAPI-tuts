"""Middleware tests: request context, CORS and rate limiting."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from app.config import settings
from app.main import create_app
from app.rate_limit import build_limiter
from tests.conftest import API


@asynccontextmanager
async def client_for(target: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=target)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


def app_with_budget(limit: str = "3/minute", **overrides: object) -> FastAPI:
    """A separate app whose limiter uses `limit` instead of the suite's budget."""
    config = settings.model_copy(
        update={"rate_limit_default": limit, "rate_limit_storage_uri": "memory://"} | overrides
    )
    return create_app(limiter=build_limiter(config))


# --- request context --------------------------------------------------------


async def test_generated_request_id_is_returned(client):
    response = await client.get(f"{API}/stats")
    assert response.status_code == 200
    assert response.headers["x-request-id"]


async def test_inbound_request_id_is_echoed(client):
    response = await client.get(f"{API}/stats", headers={"X-Request-ID": "trace-abc-123"})
    assert response.headers["x-request-id"] == "trace-abc-123"


async def test_oversized_request_id_is_replaced(client):
    response = await client.get(f"{API}/stats", headers={"X-Request-ID": "x" * 500})
    returned = response.headers["x-request-id"]
    assert returned != "x" * 500
    assert 0 < len(returned) <= 128


async def test_process_time_header_is_present(client):
    response = await client.get(f"{API}/stats")
    assert float(response.headers["x-process-time-ms"]) >= 0


async def test_error_bodies_carry_the_same_request_id_as_the_header(client):
    response = await client.get(f"{API}/books/9999")
    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "not_found"
    assert body["request_id"] == response.headers["x-request-id"]
    assert body["request_id"] != "-"


# --- CORS -------------------------------------------------------------------


async def test_cors_preflight_is_allowed(client):
    response = await client.options(
        f"{API}/books",
        headers={"Origin": "http://example.com", "Access-Control-Request-Method": "POST"},
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "*"


# --- rate limiting ----------------------------------------------------------


async def test_requests_within_budget_pass(client):
    async with client_for(app_with_budget("3/minute")) as http_client:
        codes = [(await http_client.get(f"{API}/stats")).status_code for _ in range(3)]
    assert codes == [200, 200, 200]


async def test_request_over_budget_is_rejected(client):
    async with client_for(app_with_budget("3/minute")) as http_client:
        for _ in range(3):
            assert (await http_client.get(f"{API}/stats")).status_code == 200
        blocked = await http_client.get(f"{API}/stats")

    assert blocked.status_code == 429
    body = blocked.json()
    assert body["code"] == "rate_limited"
    assert "Rate limit exceeded" in body["detail"]
    # The rejection still passed through the request-context middleware.
    assert body["request_id"] == blocked.headers["x-request-id"]
    assert int(blocked.headers["retry-after"]) >= 1
    assert blocked.headers["x-ratelimit-limit"] == "3"
    assert blocked.headers["x-ratelimit-remaining"] == "0"


async def test_budget_is_shared_across_endpoints(client):
    """One budget per client, not one per path."""
    async with client_for(app_with_budget("3/minute")) as http_client:
        for _ in range(3):
            assert (await http_client.get(f"{API}/stats")).status_code == 200
        # A different endpoint must not hand out a fresh budget.
        other = await http_client.get(f"{API}/books")
    assert other.status_code == 429


async def test_health_probe_is_exempt_from_rate_limiting(client):
    async with client_for(app_with_budget("1/minute")) as http_client:
        codes = [(await http_client.get(f"{API}/health")).status_code for _ in range(5)]
    assert codes == [200] * 5


async def test_docs_are_exempt_from_rate_limiting(client):
    async with client_for(app_with_budget("1/minute")) as http_client:
        codes = [(await http_client.get("/docs")).status_code for _ in range(3)]
    assert codes == [200, 200, 200]


async def test_rate_limiting_can_be_disabled():
    app = app_with_budget("1/minute", rate_limit_enabled=False)
    async with client_for(app) as http_client:
        codes = [(await http_client.get(f"{API}/stats")).status_code for _ in range(5)]
    assert codes == [200] * 5


async def test_forwarded_for_is_only_trusted_when_configured(monkeypatch):
    """Spoofing X-Forwarded-For must not grant a fresh budget by default."""
    app = app_with_budget("1/minute")
    async with client_for(app) as http_client:
        first = await http_client.get(f"{API}/stats", headers={"X-Forwarded-For": "1.2.3.4"})
        second = await http_client.get(f"{API}/stats", headers={"X-Forwarded-For": "5.6.7.8"})
    assert first.status_code == 200
    assert second.status_code == 429

    # Opting in behind a trusted proxy makes the header meaningful.
    monkeypatch.setattr(settings, "trust_proxy_headers", True)
    app = app_with_budget("1/minute")
    async with client_for(app) as http_client:
        a = await http_client.get(f"{API}/stats", headers={"X-Forwarded-For": "1.2.3.4"})
        b = await http_client.get(f"{API}/stats", headers={"X-Forwarded-For": "5.6.7.8"})
    assert a.status_code == 200
    assert b.status_code == 200
