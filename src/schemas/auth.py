"""Pydantic-контракты слоя авторизации."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RegIn(BaseModel):
    """Регистрация локального аккаунта."""

    login: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)
    email: str | None = Field(default=None, max_length=255)


class LoginIn(BaseModel):
    """Вход по логину и паролю."""

    login: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class RefreshIn(BaseModel):
    """Обновление пары токенов по refresh-токену."""

    refresh_token: str


class TokenPair(BaseModel):
    """Выданная пара токенов."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # TTL access-токена, секунды


class AccOut(BaseModel):
    """Публичное представление аккаунта."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    login: str
    email: str | None = None
    is_active: bool
    is_verified: bool
    role: str | None = None
    created_at: datetime

    @classmethod
    def from_account(cls, acc) -> "AccOut":  # noqa: ANN001 — models.Account
        """Собрать DTO из ORM-аккаунта (роль — по имени)."""
        return cls(
            id=acc.id,
            login=acc.login,
            email=acc.email,
            is_active=acc.is_active,
            is_verified=acc.is_verified,
            role=acc.role.name if acc.role else None,
            created_at=acc.created_at,
        )


__all__ = ["RegIn", "LoginIn", "RefreshIn", "TokenPair", "AccOut"]
