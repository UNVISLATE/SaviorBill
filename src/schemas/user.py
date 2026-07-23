"""Схемы пользователей для админ-API (Request/Response)."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class User(BaseModel):
    """User account."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    login: str
    email: str | None = None
    is_active: bool
    is_verified: bool
    role_id: int | None = None
    balance: Decimal
    bonus_balance: Decimal
    ref_code: str | None = None
    referred_by: int | None = None
    created_at: datetime
    last_login: datetime | None = None

    @classmethod
    def from_model(cls, m) -> "User":  # noqa: ANN001 — UserModel
        return cls.model_validate(m)


class UserCreateAdmin(BaseModel):
    """Create a user account (admin)."""

    login: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=256)
    email: str | None = Field(default=None, max_length=255)
    role_id: int | None = Field(
        default=None, description="Starting role; defaults to 'user' if omitted"
    )


class UserPatch(BaseModel):
    """Update user account."""

    email: str | None = Field(
        default=None, max_length=255, description="New email (optional)"
    )
    role_id: int | None = Field(
        default=None,
        description="Role ID; controls block/verify",
    )
    balance: Decimal | None = Field(
        default=None, description="New main balance (optional)"
    )
    bonus_balance: Decimal | None = Field(
        default=None, description="New bonus balance (optional)"
    )


class BalanceAdjust(BaseModel):
    """Manual balance adjustment (admin)."""

    amount: Decimal = Field(
        description="Delta to apply; positive tops up, negative deducts"
    )
    kind: Literal["main", "bonus"] = Field(description="Which balance to adjust")
    reason: str = Field(min_length=1, max_length=500, description="Audit reason")


class UserStats(BaseModel):
    """Registration counters for the admin users page header."""

    total: int
    registered_all_time: int
    registered_1d: int
    registered_7d: int
    registered_30d: int
    registered_90d: int
    registered_custom: int | None = Field(
        default=None, description="Count in [from, to] if both were given"
    )


class RegistrationsByDay(BaseModel):
    """One point of the registrations-per-day series."""

    day: str = Field(description="ISO date (YYYY-MM-DD)")
    count: int


class SessionOut(BaseModel):
    """Active login session (one refresh-token lineage) for a user."""

    jti: str
    ip: str | None
    user_agent: str | None
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime

    @classmethod
    def from_info(cls, info) -> "SessionOut":
        return cls(
            jti=info.jti,
            ip=info.ip,
            user_agent=info.user_agent,
            created_at=datetime.fromtimestamp(info.created_at, tz=timezone.utc),
            last_seen_at=datetime.fromtimestamp(info.last_seen_at, tz=timezone.utc),
            expires_at=datetime.fromtimestamp(info.exp, tz=timezone.utc),
        )


class OAuthConnAdmin(BaseModel):
    """User OAuth link."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    provider: str
    subject: str
    email: str | None = None
    created_at: datetime

    @classmethod
    def from_model(cls, m) -> "OAuthConnAdmin":  # noqa: ANN001 — UserOauthModel
        """Явное преобразование ORM-привязки в схему ответа."""
        return cls.model_validate(m)


class UserDetail(BaseModel):
    """Full user details."""

    id: int
    login: str
    email: str | None = None
    is_active: bool
    is_verified: bool
    role_id: int | None = None
    role: str | None = None
    balance: Decimal
    bonus_balance: Decimal
    ref_code: str | None = None
    referred_by: int | None = None
    created_at: datetime
    last_login: datetime | None = None
    has_pass: bool
    oauth: list[OAuthConnAdmin]
    services_count: int
    payments_count: int

    @classmethod
    def from_model(
        cls,
        m,  # noqa: ANN001 — UserModel
        oauth_conns: list,
        services_count: int,
        payments_count: int,
    ) -> "UserDetail":
        """Собрать карточку из ORM-аккаунта и связанных агрегатов.

        :arg m: аккаунт (UserModel).
        :arg oauth_conns: список OAuth-привязок.
        :arg services_count: число услуг пользователя.
        :arg payments_count: число платежей пользователя.
        :return: схема ответа.
        """
        return cls(
            id=m.id,
            login=m.login,
            email=m.email,
            is_active=m.is_active,
            is_verified=m.is_verified,
            role_id=m.role_id,
            role=m.role.name if m.role else None,
            balance=m.balance,
            bonus_balance=m.bonus_balance,
            ref_code=m.ref_code,
            referred_by=m.referred_by,
            created_at=m.created_at,
            last_login=m.last_login,
            has_pass=m.has_pass,
            oauth=[OAuthConnAdmin.from_model(c) for c in oauth_conns],
            services_count=services_count,
            payments_count=payments_count,
        )


__all__ = [
    "User",
    "UserPatch",
    "BalanceAdjust",
    "UserStats",
    "SessionOut",
    "OAuthConnAdmin",
    "UserDetail",
]
