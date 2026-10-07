"""Member schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.enums import MemberStatus
from app.schemas.summaries import ORMModel


class MemberCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=160)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=40)
    status: MemberStatus = MemberStatus.ACTIVE


class MemberUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=160)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40)
    status: MemberStatus | None = None


class MemberRead(ORMModel):
    id: int
    full_name: str
    email: str
    phone: str | None
    status: MemberStatus
    can_borrow: bool
    created_at: datetime
    updated_at: datetime
