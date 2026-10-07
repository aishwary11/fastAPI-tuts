"""Enumerations shared by the ORM models and the API schemas."""

from __future__ import annotations

from enum import StrEnum


class MemberStatus(StrEnum):
    """Whether a member is allowed to borrow books."""

    ACTIVE = "active"
    SUSPENDED = "suspended"
    INACTIVE = "inactive"


class LoanStatus(StrEnum):
    """Derived state of a loan (not stored -- computed from the timestamps)."""

    ACTIVE = "active"
    OVERDUE = "overdue"
    RETURNED = "returned"
