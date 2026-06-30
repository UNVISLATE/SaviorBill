"""Схемы пользователей для админ-API (Request/Response)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class User(BaseModel):
    """Аккаунт в админ-списке (ответ)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    login: str
    email: str | None = None
    is_active: bool
    is_verified: bool
    role_id: int | None = None
    balance: Decimal
    bonus_balance: Decimal
    created_at: datetime
    last_login: datetime | None = None

    @classmethod
    def from_model(cls, m) -> "User":  # noqa: ANN001 — UserModel
        """Явное преобразование ORM-аккаунта в схему ответа."""
        return cls.model_validate(m)


class UserPatch(BaseModel):
    """Частичное редактирование аккаунта (только переданные поля)."""

    email: str | None = None
    is_active: bool | None = None
    is_verified: bool | None = None
    role_id: int | None = None
    balance: Decimal | None = None
    bonus_balance: Decimal | None = None


__all__ = ["User", "UserPatch"]
