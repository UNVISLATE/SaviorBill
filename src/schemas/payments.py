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

    amount: Decimal = Field(gt=0, description="Сумма платежа > 0 (обязательно)")
    provider: str = Field(description="slug платёжного провайдера (обязательно)")
    target: str = Field(
        default=PayTarget.BALANCE,
        description="Назначение: balance (пополнение) | service (оплата услуги). Опционально",
    )
    service_id: int | None = Field(
        default=None, description="ID услуги, обязателен при target=service"
    )
    return_url: str | None = Field(
        default=None,
        description="URL возврата после оплаты, если провайдер его поддерживает (опционально)",
    )


class Payment(BaseModel):
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

    @classmethod
    def from_model(cls, m) -> "Payment":  # noqa: ANN001 — UserPaymentsModel
        """Явное преобразование ORM-платежа в публичную схему.

        :arg m: модель платежа.
        :return: схема ответа.
        """
        return cls.model_validate(m)


class PaymentAdmin(Payment):
    """Платёж с приватными данными (для администраторов)."""

    account_id: int
    external_id: str | None = None
    private_data: dict


class Balance(BaseModel):
    """Текущий баланс аккаунта."""

    balance: Decimal
    bonus_balance: Decimal
    currency: str = "RUB"


__all__ = ["PaymentCreate", "Payment", "PaymentAdmin", "Balance"]
