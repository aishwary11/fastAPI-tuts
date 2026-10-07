"""Rate limiting, delegated to `slowapi` (which builds on the `limits` library).

Why a library rather than hand-rolled counters:

* keeping **one shared budget across workers** is a storage problem, not a
  middleware problem -- `limits` already ships the atomic Redis algorithms, and
  switching ``RATE_LIMIT_STORAGE_URI`` from ``memory://`` to ``redis://`` is the
  whole change;
* ``in_memory_fallback`` keeps a limit enforced from process memory while the
  shared store is unreachable, instead of silently failing open.

Why there is still a small middleware here: slowapi's own middleware finds the
route handler by walking ``app.routes`` looking for ``route.endpoint``. FastAPI
0.142 represents included routers as lazy ``_IncludedRouter`` objects that expose
no ``endpoint`` (and no ``routes``), so that lookup returns ``None`` and slowapi
treats **every request as exempt** -- it fails open, silently. Rather than patch
around a private lookup, this middleware resolves the request itself and calls
the limiter directly; all counting, storage, fallback and header logic is still
the library's.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, Request
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.datastructures import MutableHeaders
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import Settings, settings

MEMORY_STORAGE_PREFIX = "memory://"

ExceededHandler = Callable[[Request, RateLimitExceeded], "Response | Awaitable[Response]"]


def client_identifier(request: Request) -> str:
    """Identify the caller for rate-limiting purposes.

    ``X-Forwarded-For`` is only consulted when ``TRUST_PROXY_HEADERS`` is on,
    because otherwise any client could present a fresh identity per request and
    never be limited.
    """
    from slowapi.util import get_remote_address

    if settings.trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            first_hop = forwarded.split(",")[0].strip()
            if first_hop:
                return first_hop
    return get_remote_address(request)


def build_limiter(config: Settings | None = None) -> Limiter:
    """Create a limiter from configuration."""
    config = config or settings
    shared_store = not config.rate_limit_storage_uri.startswith(MEMORY_STORAGE_PREFIX)
    return Limiter(
        key_func=client_identifier,
        # application_limits give one budget per client across the whole API.
        # (default_limits would key the budget per path, so a client could still
        # make 10 requests to each of the 16 endpoints.)
        application_limits=[config.rate_limit_default],
        storage_uri=config.rate_limit_storage_uri,
        # If the shared store goes down, keep enforcing the same budget from
        # process memory rather than letting every request through.
        in_memory_fallback=[config.rate_limit_default],
        in_memory_fallback_enabled=shared_store,
        # Emit X-RateLimit-* / Retry-After so clients can see their budget.
        headers_enabled=True,
        enabled=config.rate_limit_enabled,
    )


def unmetered_paths() -> frozenset[str]:
    """Paths that stay reachable no matter how busy a client is.

    The health probe drives monitoring and the docs surface is how humans
    explore the API; throttling either is a footgun.
    """
    return frozenset(
        {
            "/",
            "/docs",
            "/docs/oauth2-redirect",
            "/redoc",
            f"{settings.api_v1_prefix}/openapi.json",
            f"{settings.api_v1_prefix}/health",
        }
    )


class RateLimitMiddleware:
    """Evaluate the limiter for every metered request."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        limiter: Limiter,
        unmetered: frozenset[str] | None = None,
        handler: ExceededHandler = _rate_limit_exceeded_handler,
    ) -> None:
        self.app = app
        self.limiter = limiter
        self.unmetered = unmetered if unmetered is not None else unmetered_paths()
        self.handler = handler

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") in self.unmetered:
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        try:
            # Passing no endpoint means the URL is used as the limit key and the
            # configured default limits apply.
            self.limiter._check_request_limit(request, None, True)
        except RateLimitExceeded as exc:
            # Raised inside the middleware, so Starlette's exception middleware
            # (which sits further in) never sees it -- invoke the handler here.
            response = self.handler(request, exc)
            if inspect.isawaitable(response):
                response = await response
            await response(scope, receive, send)
            return

        current_limit: Any | None = getattr(request.state, "view_rate_limit", None)

        async def send_with_budget(message: Message) -> None:
            if message["type"] == "http.response.start" and current_limit is not None:
                # MutableHeaders mutates the raw header list in place, which is
                # what slowapi's header injection expects.
                headers = MutableHeaders(raw=message["headers"])
                self.limiter._inject_asgi_headers(headers, current_limit)
            await send(message)

        await self.app(scope, receive, send_with_budget)


def install_rate_limiting(app: FastAPI, limiter: Limiter) -> None:
    """Attach the limiter and its middleware to an app."""
    app.state.limiter = limiter
    app.add_middleware(
        RateLimitMiddleware,
        limiter=limiter,
        unmetered=unmetered_paths(),
        handler=app.exception_handlers.get(RateLimitExceeded, _rate_limit_exceeded_handler),
    )


__all__ = [
    "RateLimitMiddleware",
    "build_limiter",
    "client_identifier",
    "install_rate_limiting",
    "unmetered_paths",
]
