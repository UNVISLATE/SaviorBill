"""Pydantic-контракты слоя авторизации."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class Reg(BaseModel):
    """Регистрация локального аккаунта."""

    login: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)
    email: str | None = Field(default=None, max_length=255)


class Login(BaseModel):
    """Вход по логину и паролю."""

    login: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class Refresh(BaseModel):
    """Обновление пары токенов по refresh-токену."""

    refresh_token: str


class TokenPair(BaseModel):
    """Выданная пара токенов."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # TTL access-токена, секунды


class PassResetRequest(BaseModel):
    """Запрос сброса пароля (по email)."""

    email: str = Field(max_length=255)


class PassResetConfirm(BaseModel):
    """Подтверждение сброса пароля новым значением."""

    token: str
    password: str = Field(min_length=8, max_length=128)


class Account(BaseModel):
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
    def from_account(cls, acc) -> "Account":  # noqa: ANN001 — models.UserModel
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


class AdminMe(BaseModel):
    """Профиль текущего администратора с правами (для админ-панели)."""

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
    "Account",
    "AdminMe",
]
