"""Middleware tests: request context, CORS and rate limiting."""

from __future__ import annotations

import asyncio

from app.config import settings
from app.main import app
from tests.conftest import API

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


async def test_successful_responses_advertise_the_budget(client):
    response = await client.get(f"{API}/stats")
    assert response.headers["x-ratelimit-limit"] == str(settings.rate_limit_requests)
    assert int(response.headers["x-ratelimit-remaining"]) == settings.rate_limit_requests - 1


async def test_rate_limit_allows_ten_requests_then_returns_429(client, monkeypatch):
    """The advertised 10-per-minute budget, driven through the real ASGI app."""
    monkeypatch.setattr(settings, "rate_limit_requests", 10)
    monkeypatch.setattr(settings, "rate_limit_window_seconds", 60)
    app.state.rate_limiter.reset()

    for attempt in range(1, 11):
        response = await client.get(f"{API}/stats")
        assert response.status_code == 200, f"request {attempt} should be allowed"

    blocked = await client.get(f"{API}/stats")
    assert blocked.status_code == 429
    body = blocked.json()
    assert body["code"] == "rate_limited"
    assert "Rate limit exceeded" in body["detail"]
    assert int(blocked.headers["retry-after"]) >= 1
    assert blocked.headers["x-ratelimit-remaining"] == "0"
    # The rejection still passed through the request-context middleware.
    assert blocked.headers["x-request-id"]


async def test_rate_limit_window_recovers(client, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_requests", 1)
    monkeypatch.setattr(settings, "rate_limit_window_seconds", 1)
    app.state.rate_limiter.reset()

    assert (await client.get(f"{API}/stats")).status_code == 200
    assert (await client.get(f"{API}/stats")).status_code == 429

    await asyncio.sleep(1.1)
    assert (await client.get(f"{API}/stats")).status_code == 200


async def test_health_probe_is_exempt_from_rate_limiting(client, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_requests", 1)
    app.state.rate_limiter.reset()

    for _ in range(5):
        assert (await client.get(f"{API}/health")).status_code == 200


async def test_rate_limiting_can_be_disabled(client, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_requests", 1)
    monkeypatch.setattr(settings, "rate_limit_enabled", False)
    app.state.rate_limiter.reset()

    for _ in range(5):
        assert (await client.get(f"{API}/stats")).status_code == 200


async def test_forwarded_for_is_only_trusted_when_configured(client, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_requests", 1)
    app.state.rate_limiter.reset()

    # Spoofing the header must not grant a fresh budget by default.
    first = await client.get(f"{API}/stats", headers={"X-Forwarded-For": "1.2.3.4"})
    second = await client.get(f"{API}/stats", headers={"X-Forwarded-For": "5.6.7.8"})
    assert first.status_code == 200
    assert second.status_code == 429

    # Opting in behind a trusted proxy makes the header meaningful.
    monkeypatch.setattr(settings, "trust_proxy_headers", True)
    app.state.rate_limiter.reset()
    allowed = await client.get(f"{API}/stats", headers={"X-Forwarded-For": "1.2.3.4"})
    other_client = await client.get(f"{API}/stats", headers={"X-Forwarded-For": "5.6.7.8"})
    assert allowed.status_code == 200
    assert other_client.status_code == 200
