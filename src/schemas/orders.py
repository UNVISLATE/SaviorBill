"""Контракты заказов (выданных услуг)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class OrderCreate(BaseModel):
    """Заказ услуги. ``promocode`` — опциональная скидка (kind=discount)."""

    service_id: int
    promocode: str | None = Field(default=None, max_length=64)
    # Доп. параметры от клиента, мёрджатся поверх Service.params.
    params: dict | None = None


class Order(BaseModel):
    """Публичное представление заказа (без приватных данных)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    service_id: int
    payment_id: int | None = None
    status: str
    price: Decimal
    discount: Decimal
    public_data: dict
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

    account_id: int
    service_id: int
    params: dict | None = None
    # Списать стоимость с баланса пользователя (по умолчанию — нет, дарим).
    charge: bool = False


__all__ = ["OrderCreate", "Order", "OrderAdmin", "OrderGrant"]
