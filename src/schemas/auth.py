"""Pydantic-контракты слоя авторизации."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


def _media_url(token: str | None) -> str | None:
    """Относительный URL медиа (см. ``schemas.media``)."""
    return f"/api/media/{token}" if token else None


class Reg(BaseModel):
    """Local account registration."""

    login: str = Field(
        min_length=3, max_length=64, description="Login (3–64 chars)"
    )
    password: str = Field(
        min_length=8, max_length=128, description="Password (8–128 chars)"
    )
    email: str | None = Field(
        default=None, max_length=255, description="Email (optional)"
    )
    ref_code: str | None = Field(
        default=None,
        max_length=16,
        description="Referrer code (optional)",
    )


class Login(BaseModel):
    """Login by username or email."""

    login: str = Field(
        min_length=3,
        max_length=64,
        description="Login or email",
    )
    password: str = Field(
        min_length=1, max_length=128, description="Password"
    )


class Refresh(BaseModel):
    """Refresh token pair."""

    refresh_token: str = Field(description="Refresh token")


class TokenPair(BaseModel):
    """Issued token pair."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # TTL access-токена, секунды
    is_active: bool = True  # False = аккаунт забанен (роль banned/RBAC урезан)


class PassResetRequest(BaseModel):
    """Password reset request."""

    email: str = Field(max_length=255, description="Account email")


class PassResetConfirm(BaseModel):
    """Confirm password reset."""

    email: str | None = Field(
        default=None,
        max_length=255,
        description="Account email; required for code mode, optional for a token link",
    )
    code: str = Field(
        min_length=6,
        max_length=64,
        description="Reset code (digits) or token from the email, depending on "
        "the `password.reset.method` setting",
    )
    password: str = Field(
        min_length=8,
        max_length=128,
        description="New password (8–128 chars)",
    )


class EmailVerifyConfirm(BaseModel):
    """Confirm email by code."""

    code: str = Field(
        min_length=4,
        max_length=10,
        description=(
            "Email code (`mail.code_digits`, default 4)"
        ),
    )


class Account(BaseModel):
    """Current account profile."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    login: str
    email: str | None = None
    is_active: bool
    is_verified: bool
    role: str | None = None
    ref_code: str | None = None
    created_at: datetime
    last_login: datetime | None = None
    balance: Decimal
    bonus_balance: Decimal
    avatar_media_id: int | None = None
    avatar_url: str | None = None
    oauth_providers: list[str] = Field(
        default_factory=list,
        description="Linked OAuth provider slugs",
    )

    @classmethod
    def from_account(
        cls, acc, *, oauth_providers: list[str] | None = None
    ) -> "Account":  # noqa: ANN001 — models.UserModel
        """Собрать DTO из ORM-аккаунта (роль — по имени).

        :arg acc: ORM-аккаунт (``avatar_media`` должен быть подгружен — это
            обеспечивает ``lazy="joined"`` на модели, доп. запрос не нужен).
        :arg oauth_providers: slugs привязанных провайдеров (передаются
            отдельно — требуют отдельного запроса к ``oauth_conns``, схема
            их сама не запрашивает).
        """
        return cls(
            id=acc.id,
            login=acc.login,
            email=acc.email,
            is_active=acc.is_active,
            is_verified=acc.is_verified,
            role=acc.role.name if acc.role else None,
            ref_code=acc.ref_code,
            created_at=acc.created_at,
            last_login=acc.last_login,
            balance=acc.balance,
            bonus_balance=acc.bonus_balance,
            avatar_media_id=acc.avatar_media_id,
            avatar_url=_media_url(acc.avatar_media.token if acc.avatar_media else None),
            oauth_providers=list(oauth_providers or []),
        )


class MePatch(BaseModel):
    """Update current account."""

    login: str | None = Field(
        default=None, min_length=3, max_length=64, description="New login (optional)"
    )
    email: str | None = Field(
        default=None,
        max_length=255,
        description="New email; may reset verification",
    )


class PasswordChange(BaseModel):
    """Change password."""

    current_password: str | None = Field(
        default=None,
        max_length=128,
        description="Current password (required if set)",
    )
    new_password: str = Field(
        min_length=8, max_length=128, description="New password (8–128 chars)"
    )


class AvatarSet(BaseModel):
    """Set avatar."""

    media_id: int | None = Field(
        description=(
            "Uploaded media ID; null removes avatar"
        )
    )


class AdminMe(BaseModel):
    """Current admin profile."""

    id: int
    login: str
    email: str | None = None
    role: str | None = None
    perms: dict

    @classmethod
    def from_account(cls, acc) -> "AdminMe":  # noqa: ANN001 — models.UserModel
        """Собрать DTO из ORM-аккаунта с деревом прав его роли."""
        return cls(
            id=acc.id,
            login=acc.login,
            email=acc.email,
            role=acc.role.name if acc.role else None,
            perms=(acc.role.perms if acc.role else {}) or {},
        )


__all__ = [
    "Reg",
    "Login",
    "Refresh",
    "TokenPair",
    "PassResetRequest",
    "PassResetConfirm",
    "EmailVerifyConfirm",
    "Account",
    "MePatch",
    "PasswordChange",
    "AvatarSet",
    "AdminMe",
]
