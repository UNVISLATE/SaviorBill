"""Схемы пользователей для админ-API (Request/Response)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class User(BaseModel):
    """Аккаунт пользователя (ответ)."""

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


class UserPatch(BaseModel):
    """Частичное редактирование аккаунта (только переданные поля).

    Активность/верификация — производные от роли, поэтому меняются через
    ``role_id`` (напр. назначить роль ``banned`` = заблокировать, ``user`` =
    верифицировать), а не отдельными флагами.
    """

    email: str | None = Field(
        default=None, max_length=255, description="Новый email (опционально)"
    )
    role_id: int | None = Field(
        default=None,
        description=(
            "ID роли (опционально). Управляет активностью/верификацией: "
            "роль banned = блокировка, user = верификация."
        ),
    )
    balance: Decimal | None = Field(
        default=None, description="Новый основной баланс (опционально)"
    )
    bonus_balance: Decimal | None = Field(
        default=None, description="Новый бонусный баланс (опционально)"
    )


class OAuthConnAdmin(BaseModel):
    """OAuth-привязка пользователя (для админ-просмотра)."""

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
    """Полная карточка пользователя для администратора."""

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


__all__ = ["User", "UserPatch", "OAuthConnAdmin", "UserDetail"]
