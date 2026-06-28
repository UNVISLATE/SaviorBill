"""Контракты платежей и баланса."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from enums import PayTarget


class PaymentCreate(BaseModel):
    """Создать платёж через провайдера.

    ``target=balance`` — пополнить баланс; ``target=service`` — оплатить
    конкретную услугу ``service_id`` (она будет выдана по успешной оплате).
    """

    amount: Decimal = Field(gt=0)
    provider: str = Field(description="slug платёжного провайдера")
    target: str = Field(default=PayTarget.BALANCE, description="balance | service")
    service_id: int | None = Field(default=None, description="для target=service")
    params: dict | None = Field(default=None, description="доп. параметры услуги")
    return_url: str | None = None


class PaymentOut(BaseModel):
    """Платёж (публичная часть, в т.ч. ссылка на оплату в public_data)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    provider: str
    amount: Decimal
    currency: str
    status: str
    target: str
    user_svc_id: int | None = None
    public_data: dict
    created_at: datetime


class PaymentAdminOut(PaymentOut):
    """Платёж с приватными данными (для администраторов)."""

    account_id: int
    external_id: str | None = None
    private_data: dict


class BalanceOut(BaseModel):
    """Текущий баланс аккаунта."""

    balance: Decimal
    bonus_balance: Decimal
    currency: str = "RUB"


__all__ = ["PaymentCreate", "PaymentOut", "PaymentAdminOut", "BalanceOut"]
