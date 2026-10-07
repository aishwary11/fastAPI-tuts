"""Async SQLAlchemy engine, session factory and FastAPI session dependency."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings


def _engine_kwargs() -> dict[str, object]:
    kwargs: dict[str, object] = {
        "echo": settings.db_echo,
        "pool_pre_ping": True,
        "future": True,
    }
    # SQLite (used by the test suite) does not accept pool sizing arguments.
    if not settings.async_database_url.startswith("sqlite"):
        kwargs.update(
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_recycle=settings.db_pool_recycle,
        )
    return kwargs


engine: AsyncEngine = create_async_engine(settings.async_database_url, **_engine_kwargs())

# `expire_on_commit=False` keeps ORM instances usable after a commit so that
# route handlers can serialise the object they just persisted.
SessionFactory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a transactional database session."""
    async with SessionFactory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    """Close the connection pool on application shutdown."""
    await engine.dispose()
