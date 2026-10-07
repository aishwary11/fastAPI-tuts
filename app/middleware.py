"""Cross-cutting HTTP middleware.

Written as raw ASGI middleware rather than ``BaseHTTPMiddleware``: it wraps the
whole request/response cycle without an extra task and without breaking
streaming responses.
"""

from __future__ import annotations

import logging
import time
from contextvars import ContextVar
from typing import Any
from uuid import uuid4

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger("library.access")

REQUEST_ID_HEADER = "X-Request-ID"
PROCESS_TIME_HEADER = "X-Process-Time-Ms"

#: The current request's id. Set by :class:`RequestContextMiddleware`, so any
#: code running inside a request (including the exception handlers) can read it.
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


class RequestContextMiddleware:
    """Attach a request id, time the request and emit an access log line.

    * honours an inbound ``X-Request-ID`` (so ids survive across services),
    * generates one when the client did not send it,
    * always echoes it back along with the server-side duration.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = self._incoming_request_id(scope) or str(uuid4())
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        status_code = 500

        async def send_with_context(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = MutableHeaders(scope=message)
                headers.append(REQUEST_ID_HEADER, request_id)
                headers.append(PROCESS_TIME_HEADER, f"{(time.perf_counter() - started) * 1000:.2f}")
            await send(message)

        try:
            await self.app(scope, receive, send_with_context)
        finally:
            duration_ms = (time.perf_counter() - started) * 1000
            logger.info(
                "%s %s -> %s (%.2f ms) request_id=%s",
                scope.get("method", "-"),
                scope.get("path", "-"),
                status_code,
                duration_ms,
                request_id,
            )
            request_id_var.reset(token)

    @staticmethod
    def _incoming_request_id(scope: Scope) -> str | None:
        for key, value in scope.get("headers", []):
            if key == b"x-request-id":
                candidate = value.decode("latin-1").strip()
                # Reject absurd values so they cannot poison logs or headers.
                if candidate and len(candidate) <= 128:
                    return candidate
                return None
        return None


def current_request_id() -> str:
    """The request id of the in-flight request (``"-"`` outside a request)."""
    return request_id_var.get()


def build_cors_options(allow_origins: list[str]) -> dict[str, Any]:
    """Keyword arguments for Starlette's ``CORSMiddleware``.

    Credentials stay disabled: the API is token-less, and ``allow_credentials``
    combined with a wildcard origin is rejected by browsers anyway.
    """
    wildcard = allow_origins == ["*"]
    return {
        "allow_origins": allow_origins,
        "allow_credentials": not wildcard,
        "allow_methods": ["*"],
        "allow_headers": ["*"],
        "expose_headers": [REQUEST_ID_HEADER, PROCESS_TIME_HEADER],
    }


__all__ = [
    "PROCESS_TIME_HEADER",
    "REQUEST_ID_HEADER",
    "RequestContextMiddleware",
    "build_cors_options",
    "current_request_id",
]
