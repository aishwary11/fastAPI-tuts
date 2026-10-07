"""Health and statistics endpoints."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app import __version__
from app.api.deps import SessionDep
from app.schemas.stats import LibraryStats
from app.services import stats as service

router = APIRouter(tags=["system"])


@router.get("/health", summary="Liveness / database readiness probe")
async def health(session: SessionDep):
    try:
        await session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "database": "unreachable"},
        )
    return {"status": "ok", "database": "reachable", "version": __version__}


@router.get("/stats", response_model=LibraryStats, summary="Library-wide statistics")
async def library_stats(session: SessionDep):
    return await service.library_stats(session)
