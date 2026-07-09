"""Схема пользователя для контекста Lua (все поля учётки + активированная услуга)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_serializer


class LuaUsvc(BaseModel):
    """Activated service data for Lua user."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    service_id: int
    payment_id: int | None = None
    status: str
    price: Decimal
    discount: Decimal
    duration: int | None = None
    actions: list = []
    expires_at: datetime | None = None
    public_data: dict = {}
    private_data: dict = {}
    product_key: str | None = None
    product_kind: str | None = None
    # Транзитные кастом-параметры заказа (не хранятся в БД).
    params: dict = {}

    @field_serializer("price", "discount")
    def _money(self, v: Decimal) -> str:
        return str(v)

    @field_serializer("expires_at")
    def _ts(self, v: datetime | None) -> int | None:
        return int(v.timestamp()) if v else None


class LuaUser(BaseModel):
    """User data for Lua."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    login: str
    email: str | None = None
    is_active: bool = True
    is_verified: bool = False
    role: str | None = None
    role_id: int | None = None
    balance: Decimal = Decimal("0")
    bonus_balance: Decimal = Decimal("0")
    created_at: datetime | None = None
    last_login: datetime | None = None
    service: LuaUsvc | None = None
    payment: int | None = None

    @field_serializer("balance", "bonus_balance")
    def _money(self, v: Decimal) -> str:
        return str(v)

    @field_serializer("created_at", "last_login")
    def _ts(self, v: datetime | None) -> int | None:
        return int(v.timestamp()) if v else None

    @classmethod
    def from_model(cls, acc, usvc=None) -> "LuaUser":  # noqa: ANN001 — ORM
        """Собрать из ORM-аккаунта (+опц. активированной услуги).

        :arg acc: аккаунт (UserModel).
        :arg usvc: выданная услуга пользователя (UserServicesModel) или None.
        :return: схема пользователя для Lua.
        """
        data = cls(
            id=acc.id,
            login=acc.login,
            email=acc.email,
            is_active=acc.is_active,
            is_verified=acc.is_verified,
            role=acc.role.name if getattr(acc, "role", None) else None,
            role_id=acc.role_id,
            balance=acc.balance,
            bonus_balance=acc.bonus_balance,
            created_at=acc.created_at,
            last_login=acc.last_login,
        )
        if usvc is not None:
            data.service = LuaUsvc.model_validate(usvc)
            data.service.params = getattr(usvc, "order_params", {}) or {}
            data.payment = usvc.payment_id
        return data


__all__ = ["LuaUser", "LuaUsvc"]
