"""Aggregate router for API version 1."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import authors, books, loans, members, system

api_router = APIRouter()
api_router.include_router(system.router)
api_router.include_router(authors.router)
api_router.include_router(books.router)
api_router.include_router(members.router)
api_router.include_router(loans.router)
