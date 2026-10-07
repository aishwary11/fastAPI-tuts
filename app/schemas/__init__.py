"""Pydantic schemas (request bodies, query params and response models)."""

from app.schemas.author import AuthorCreate, AuthorDetail, AuthorRead, AuthorUpdate
from app.schemas.book import BookCreate, BookRead, BookUpdate
from app.schemas.common import Message, Page, PaginationParams, pagination_params
from app.schemas.loan import LoanCreate, LoanRead
from app.schemas.member import MemberCreate, MemberRead, MemberUpdate
from app.schemas.stats import LibraryStats
from app.schemas.summaries import AuthorSummary, BookSummary, MemberSummary, ORMModel

__all__ = [
    "AuthorCreate",
    "AuthorDetail",
    "AuthorRead",
    "AuthorSummary",
    "AuthorUpdate",
    "BookCreate",
    "BookRead",
    "BookSummary",
    "BookUpdate",
    "LibraryStats",
    "LoanCreate",
    "LoanRead",
    "MemberCreate",
    "MemberRead",
    "MemberSummary",
    "MemberUpdate",
    "Message",
    "ORMModel",
    "Page",
    "PaginationParams",
    "pagination_params",
]
