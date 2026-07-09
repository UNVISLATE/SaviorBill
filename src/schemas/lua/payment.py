"""Схемы платежа и провайдера для контекста Lua."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_serializer


class LuaProvider(BaseModel):
    """Payment provider data for Lua."""

    slug: str
    title: str | None = None
    currency: str = "RUB"
    enabled: bool = True
    secrets: dict = {}
    extra: dict = {}

    @classmethod
    def from_model(cls, prov, secrets: dict) -> "LuaProvider":  # noqa: ANN001 — ORM
        """Собрать из ORM-провайдера и уже расшифрованных секретов."""
        return cls(
            slug=prov.slug,
            title=prov.title,
            currency=prov.currency,
            enabled=prov.enabled,
            secrets=secrets or {},
            extra=prov.extra or {},
        )


class LuaPayment(BaseModel):
    """Payment data for Lua."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    provider: str
    amount: Decimal
    currency: str = "RUB"
    status: str
    target: str
    user_svc_id: int | None = None
    external_id: str | None = None
    public_data: dict = {}
    private_data: dict = {}
    created_at: datetime | None = None
    paid_at: datetime | None = None
    # Ссылка возврата (передаётся при инициализации; не хранится в БД).
    return_url: str | None = None
    provider_data: LuaProvider | None = None

    @field_serializer("amount")
    def _money(self, v: Decimal) -> str:
        return str(v)

    @field_serializer("created_at", "paid_at")
    def _ts(self, v: datetime | None) -> int | None:
        return int(v.timestamp()) if v else None

    @classmethod
    def from_model(
        cls, m, provider: LuaProvider | None = None, return_url: str | None = None
    ) -> "LuaPayment":  # noqa: ANN001 — UserPaymentsModel
        """Собрать из ORM-платежа (+опц. данные провайдера и return_url)."""
        data = cls.model_validate(m)
        data.provider_data = provider
        data.return_url = return_url
        return data


__all__ = ["LuaPayment", "LuaProvider"]
