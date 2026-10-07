"""FastAPI application entry point."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app import __version__
from app.api.v1 import api_router
from app.config import settings
from app.database import dispose_engine
from app.exceptions import DomainError
from app.middleware import RequestContextMiddleware, build_cors_options, current_request_id
from app.rate_limit import RateLimitMiddleware, SlidingWindowRateLimiter

logger = logging.getLogger("library")

DESCRIPTION = """
A small library management API.

* **Catalogue** -- authors and books, with per-copy availability tracking.
* **Members** -- registration and membership status.
* **Circulation** -- borrow, return and renew books; duplicate active loans are
  rejected and availability is enforced inside a database transaction.
"""

# Endpoints excluded from rate limiting: the health probe and the docs surface.
UNMETERED_PATHS = frozenset(
    {
        "/",
        "/docs",
        "/docs/oauth2-redirect",
        "/redoc",
        f"{settings.api_v1_prefix}/health",
        f"{settings.api_v1_prefix}/openapi.json",
    }
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("%s v%s starting (env=%s)", settings.app_name, __version__, settings.environment)
    yield
    await dispose_engine()
    logger.info("%s shut down", settings.app_name)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _domain_error(_: Request, exc: DomainError) -> JSONResponse:
        """Business-rule violations raised by the service layer."""
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "detail": exc.message,
                "code": exc.code,
                "request_id": current_request_id(),
            },
        )

    @app.exception_handler(IntegrityError)
    async def _integrity_error(_: Request, exc: IntegrityError) -> JSONResponse:
        """Safety net for constraint violations not caught by a service."""
        logger.warning("Unhandled integrity error: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "detail": "The request conflicts with an existing record.",
                "code": "conflict",
                "request_id": current_request_id(),
            },
        )

    @app.exception_handler(SQLAlchemyError)
    async def _database_error(_: Request, exc: SQLAlchemyError) -> JSONResponse:
        logger.exception("Database error: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "detail": "Database unavailable.",
                "code": "database_error",
                "request_id": current_request_id(),
            },
        )


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description=DESCRIPTION,
        lifespan=lifespan,
        openapi_url=f"{settings.api_v1_prefix}/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # Middleware is applied innermost-first: the last one added ends up
    # outermost, so request context wraps rate limiting and CORS.
    app.add_middleware(CORSMiddleware, **build_cors_options(settings.cors_allow_origins))

    limiter = SlidingWindowRateLimiter()
    app.state.rate_limiter = limiter
    app.add_middleware(RateLimitMiddleware, limiter=limiter, exempt_paths=UNMETERED_PATHS)
    app.add_middleware(RequestContextMiddleware)

    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    @app.get("/", tags=["system"], summary="Service banner")
    async def root() -> dict[str, str]:
        return {
            "service": settings.app_name,
            "version": __version__,
            "docs": "/docs",
            "api": settings.api_v1_prefix,
        }

    return app


app = create_app()
