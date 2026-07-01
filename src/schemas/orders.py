"""Контракты заказов (выданных услуг)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class OrderCreate(BaseModel):
    """Заказ услуги. ``promocode`` — опциональная скидка (kind=discount)."""

    service_id: int = Field(description="ID заказываемой услуги (обязательно)")
    promocode: str | None = Field(
        default=None, max_length=64, description="Промокод-скидка (опционально)"
    )
    params: dict | None = Field(
        default=None,
        description="Доп. параметры от клиента, мёрджатся поверх Service.params (опционально)",
    )


class Order(BaseModel):
    """Публичное представление заказа (без приватных данных)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    service_id: int
    payment_id: int | None = None
    status: str
    state: str = Field(description="Состояние ЖЦ: active/frozen/stopped/expired")
    price: Decimal
    discount: Decimal
    public_data: dict
    actions: list = Field(
        default_factory=list,
        description="Поддерживаемые действия услуги (create/renew/stop/delete/freeze)",
    )
    expires_at: datetime | None = Field(
        default=None, description="Момент истечения (null — бессрочная)"
    )
    error: str | None = None
    created_at: datetime
    delivered_at: datetime | None = None

    @classmethod
    def from_model(cls, m) -> "Order":  # noqa: ANN001 — UserServicesModel
        """Явное преобразование ORM-заказа в публичную схему.

        :arg m: модель выданной услуги.
        :return: схема ответа.
        """
        return cls.model_validate(m)


class OrderAdmin(Order):
    """Заказ с приватными данными (для администраторов)."""

    account_id: int
    private_data: dict


class OrderGrant(BaseModel):
    """Ручная выдача услуги пользователю админом (без оплаты)."""

    account_id: int = Field(description="ID аккаунта-получателя (обязательно)")
    service_id: int = Field(description="ID выдаваемой услуги (обязательно)")
    params: dict | None = Field(
        default=None, description="Доп. параметры услуги (опционально)"
    )
    charge: bool = Field(
        default=False,
        description="Списать стоимость с баланса пользователя; по умолчанию — дарим (опционально)",
    )


__all__ = ["OrderCreate", "Order", "OrderAdmin", "OrderGrant"]
