"""Per-client rate limiting.

Implemented as raw ASGI middleware. Requests are counted in a sliding-window log
keyed by the client's address; the first request over the limit is rejected with
``429`` and a ``Retry-After`` hint.

.. warning::
   The counters live in this process's memory. Running several workers (or
   several containers) multiplies the effective limit, because each worker keeps
   its own window. For a hard global limit, back the limiter with Redis.
"""

from __future__ import annotations

import math
import threading
import time
from collections import deque
from collections.abc import Collection
from dataclasses import dataclass

from starlette.datastructures import MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import settings

DEFAULT_MAX_TRACKED_CLIENTS = 10_000

RATE_LIMIT_LIMIT_HEADER = "X-RateLimit-Limit"
RATE_LIMIT_REMAINING_HEADER = "X-RateLimit-Remaining"
RATE_LIMIT_RESET_HEADER = "X-RateLimit-Reset"


@dataclass(frozen=True, slots=True)
class RateLimitResult:
    """Outcome of a single rate-limit check."""

    allowed: bool
    limit: int
    remaining: int
    reset_after: float
    retry_after: float


class SlidingWindowRateLimiter:
    """Sliding-window log limiter backed by an in-process dict.

    A sliding window is used rather than a fixed one so a client cannot burst
    twice the limit by straddling a window boundary.
    """

    def __init__(self, max_tracked_clients: int = DEFAULT_MAX_TRACKED_CLIENTS) -> None:
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()
        self.max_tracked_clients = max_tracked_clients

    def check(
        self,
        key: str,
        *,
        limit: int,
        window: float,
        now: float | None = None,
    ) -> RateLimitResult:
        moment = time.monotonic() if now is None else now
        cutoff = moment - window

        with self._lock:
            bucket = self._hits.setdefault(key, deque())
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()

            if len(bucket) >= limit:
                # The oldest hit is what frees the next slot.
                retry_after = max(bucket[0] - cutoff, 0.0)
                return RateLimitResult(False, limit, 0, window, retry_after)

            bucket.append(moment)
            self._evict_stale(cutoff)
            return RateLimitResult(True, limit, limit - len(bucket), window, 0.0)

    def _evict_stale(self, cutoff: float) -> None:
        """Keep the dict bounded when many distinct clients appear."""
        if len(self._hits) <= self.max_tracked_clients:
            return
        for key in [key for key, hits in self._hits.items() if not hits or hits[-1] <= cutoff]:
            del self._hits[key]

    def reset(self) -> None:
        """Forget every window (used by tests)."""
        with self._lock:
            self._hits.clear()


class RateLimitMiddleware:
    """Reject requests once a client exceeds the configured budget."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        limiter: SlidingWindowRateLimiter | None = None,
        exempt_paths: Collection[str] = (),
    ) -> None:
        self.app = app
        self.limiter = limiter or SlidingWindowRateLimiter()
        self.exempt_paths = frozenset(exempt_paths)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not settings.rate_limit_enabled:
            await self.app(scope, receive, send)
            return

        # Preflight requests are exempt so browsers can negotiate CORS.
        if scope.get("method") == "OPTIONS" or scope.get("path") in self.exempt_paths:
            await self.app(scope, receive, send)
            return

        result = self.limiter.check(
            self._client_key(scope),
            limit=settings.rate_limit_requests,
            window=settings.rate_limit_window_seconds,
        )

        if not result.allowed:
            retry_after = max(1, math.ceil(result.retry_after))
            response = JSONResponse(
                status_code=429,
                content={
                    "detail": (
                        f"Rate limit exceeded: {result.limit} requests per "
                        f"{int(settings.rate_limit_window_seconds)}s. "
                        f"Retry in {retry_after}s."
                    ),
                    "code": "rate_limited",
                },
                headers=self._headers(result, retry_after=retry_after),
            )
            await response(scope, receive, send)
            return

        async def send_with_budget(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message).update(self._headers(result))
            await send(message)

        await self.app(scope, receive, send_with_budget)

    @staticmethod
    def _headers(result: RateLimitResult, retry_after: int | None = None) -> dict[str, str]:
        headers = {
            RATE_LIMIT_LIMIT_HEADER: str(result.limit),
            RATE_LIMIT_REMAINING_HEADER: str(result.remaining),
            RATE_LIMIT_RESET_HEADER: str(int(result.reset_after)),
        }
        if retry_after is not None:
            headers["Retry-After"] = str(retry_after)
        return headers

    @staticmethod
    def _client_key(scope: Scope) -> str:
        """Identify the caller.

        ``X-Forwarded-For`` is only consulted when ``TRUST_PROXY_HEADERS`` is on,
        because otherwise any client could spoof its identity and bypass the
        limit entirely.
        """
        if settings.trust_proxy_headers:
            for name, value in scope.get("headers", []):
                if name == b"x-forwarded-for":
                    first_hop = value.decode("latin-1").split(",")[0].strip()
                    if first_hop:
                        return first_hop
        client = scope.get("client")
        return client[0] if client else "unknown"


__all__ = [
    "RateLimitMiddleware",
    "RateLimitResult",
    "SlidingWindowRateLimiter",
]
