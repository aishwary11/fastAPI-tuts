"""Member model."""

from __future__ import annotations

from sqlalchemy import Enum as SAEnum
from sqlalchemy import Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin
from app.models.enums import MemberStatus

member_status_enum = SAEnum(
    MemberStatus,
    name="member_status",
    native_enum=True,
    # Persist the enum *values* ("active"), not the member names ("ACTIVE").
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
)


class Member(TimestampMixin, Base):
    __tablename__ = "members"
    __table_args__ = (Index("ix_members_email", "email", unique=True),)

    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    status: Mapped[MemberStatus] = mapped_column(
        member_status_enum,
        nullable=False,
        default=MemberStatus.ACTIVE,
        server_default=MemberStatus.ACTIVE.value,
    )

    @property
    def can_borrow(self) -> bool:
        return self.status is MemberStatus.ACTIVE
