"""Pydantic-контракты слоя авторизации."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class Reg(BaseModel):
    """Регистрация локального аккаунта."""

    login: str = Field(
        min_length=3, max_length=64, description="Логин (обязательно), 3–64 символа"
    )
    password: str = Field(
        min_length=8, max_length=128, description="Пароль (обязательно), 8–128 символов"
    )
    email: str | None = Field(
        default=None, max_length=255, description="Email (опционально)"
    )
    ref_code: str | None = Field(
        default=None,
        max_length=16,
        description="Реферальный код пригласившего (опционально)",
    )


class Login(BaseModel):
    """Вход по логину и паролю."""

    login: str = Field(min_length=3, max_length=64, description="Логин (обязательно)")
    password: str = Field(
        min_length=1, max_length=128, description="Пароль (обязательно)"
    )


class Refresh(BaseModel):
    """Обновление пары токенов по refresh-токену."""

    refresh_token: str = Field(description="Refresh-токен (обязательно)")


class TokenPair(BaseModel):
    """Выданная пара токенов."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # TTL access-токена, секунды
    is_active: bool = True  # False = аккаунт забанен (роль banned/RBAC урезан)


class PassResetRequest(BaseModel):
    """Запрос сброса пароля (по email)."""

    email: str = Field(max_length=255, description="Email аккаунта (обязательно)")


class PassResetConfirm(BaseModel):
    """Подтверждение сброса пароля кодом из письма."""

    email: str = Field(max_length=255, description="Email аккаунта (обязательно)")
    code: str = Field(
        min_length=6, max_length=6, description="6-значный код из письма (обязательно)"
    )
    password: str = Field(
        min_length=8,
        max_length=128,
        description="Новый пароль (обязательно), 8–128 символов",
    )


class EmailVerifyConfirm(BaseModel):
    """Подтверждение email числовым кодом из письма."""

    code: str = Field(
        min_length=4,
        max_length=10,
        description=(
            "Числовой код из письма (длина настраивается через `mail.code_digits`, "
            "по умолчанию 4 цифры)"
        ),
    )


class Account(BaseModel):
    """Публичное представление аккаунта."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    login: str
    email: str | None = None
    is_active: bool
    is_verified: bool
    role: str | None = None
    ref_code: str | None = None
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
            ref_code=acc.ref_code,
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
    "EmailVerifyConfirm",
    "Account",
    "AdminMe",
]
