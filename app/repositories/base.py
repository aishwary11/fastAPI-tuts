"""Generic repository helpers shared by the concrete repositories.

The repository layer owns *how* rows are fetched; the service layer owns
*what the rules are*. Routers only talk to services.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Generic, TypeVar

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import ConflictError
from app.models.base import Base

ModelT = TypeVar("ModelT", bound=Base)


@asynccontextmanager
async def guard_integrity(session: AsyncSession, message: str) -> AsyncIterator[None]:
    """Translate a database constraint violation into a 409 response."""
    try:
        yield
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictError(message) from exc


class Repository(Generic[ModelT]):
    """Thin CRUD wrapper around a single ORM model."""

    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # -- Reads ---------------------------------------------------------------
    async def get(self, entity_id: int, *, for_update: bool = False) -> ModelT | None:
        """Fetch one row by primary key.

        ``for_update`` takes a row-level lock (``SELECT ... FOR UPDATE``) so
        concurrent borrows cannot both pass the availability check.
        """
        stmt = select(self.model).where(self.model.id == entity_id)
        if for_update:
            # Lock only this table's row; eager-joined rows stay unlocked.
            stmt = stmt.with_for_update(of=self.model)
        return (await self.session.execute(stmt)).scalars().unique().one_or_none()

    async def count(self, *clauses: Any) -> int:
        stmt = select(func.count()).select_from(self.model).where(*clauses)
        return (await self.session.execute(stmt)).scalar_one()

    # -- Writes --------------------------------------------------------------
    async def add(self, **values: Any) -> ModelT:
        instance = self.model(**values)
        self.session.add(instance)
        await self._flush_refresh(instance)
        return instance

    async def save(self, instance: ModelT, values: dict[str, Any]) -> ModelT:
        for field, value in values.items():
            setattr(instance, field, value)
        await self._flush_refresh(instance)
        return instance

    async def remove(self, instance: ModelT) -> None:
        await self.session.delete(instance)
        await self.session.flush()

    # -- Internals -----------------------------------------------------------
    async def _flush_refresh(self, instance: ModelT) -> None:
        """Flush, then re-read so server defaults (timestamps) are populated."""
        await self.session.flush()
        await self.session.refresh(instance)
