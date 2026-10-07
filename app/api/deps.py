"""Shared FastAPI dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas.common import PaginationParams, pagination_params

SessionDep = Annotated[AsyncSession, Depends(get_session)]
PageDep = Annotated[PaginationParams, Depends(pagination_params)]
