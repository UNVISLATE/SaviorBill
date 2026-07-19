"""Контракты платежей и баланса."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from enums import PayTarget


class PaymentCreate(BaseModel):
    """Create payment.

    ``amount`` is required only for ``target=balance`` (arbitrary top-up
    sum chosen by the user). For ``target=service`` the price is always
    the server-side ``service.price`` — the client cannot supply/override
    it, so ``amount`` here is rejected outright rather than validated: a
    provider that trusts whatever amount it was asked to charge should
    never see anything but the authoritative price.
    """

    amount: Decimal | None = Field(
        default=None, gt=0, description="Payment amount > 0 (target=balance only)"
    )
    provider: str = Field(description="Payment provider slug")
    target: str = Field(
        default=PayTarget.BALANCE,
        description="Target: balance | service",
    )
    service_id: int | None = Field(
        default=None, description="Service ID for target=service"
    )
    return_url: str | None = Field(
        default=None,
        description="Return URL if supported (optional)",
    )

    @model_validator(mode="after")
    def _check_amount(self) -> "PaymentCreate":
        if self.target == PayTarget.BALANCE and self.amount is None:
            raise ValueError("amount is required for target=balance")
        if self.target == PayTarget.SERVICE and self.amount is not None:
            raise ValueError(
                "amount must not be supplied for target=service; "
                "price is taken from the service"
            )
        return self


class Payment(BaseModel):
    """Public payment."""

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
    """Payment with private data."""

    account_id: int
    external_id: str | None = None
    private_data: dict


class Balance(BaseModel):
    """Current account balance."""

    balance: Decimal
    bonus_balance: Decimal
    currency: str = "RUB"


__all__ = ["PaymentCreate", "Payment", "PaymentAdmin", "Balance"]
