"""Контракты платежей и баланса."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from enums import PayTarget


class PaymentCreate(BaseModel):
    """Create payment."""

    amount: Decimal | None = Field(
        default=None, gt=0, description="Payment amount > 0 (target=balance only)"
    )
    provider: str = Field(min_length=1, max_length=64, description="Payment provider slug")
    currency: str | None = Field(
        default=None, max_length=8, description="Desired payment currency (optional)"
    )
    amount_in_payment_currency: bool = Field(
        default=False,
        description="When true (target=balance only), amount is specified in selected payment currency",
    )
    target: Literal["balance", "service", "renew", "upgrade"] = Field(
        default=PayTarget.BALANCE,
        description="Target: balance | service | renew | upgrade",
    )
    service_id: int | None = Field(
        default=None, ge=1, description="Service ID for target=service"
    )
    user_svc_id: int | None = Field(
        default=None, ge=1, description="Existing user service ID for target=renew|upgrade"
    )
    custom_amount: Decimal | None = Field(
        default=None, gt=0, description="Arbitrary sum for price_type=custom (target=service only)"
    )
    tier_code: str | None = Field(
        default=None, max_length=64, description="Subtier code for price_type=tiered (target=service only)"
    )
    components: dict[str, Any] | None = Field(
        default=None, description="Component quantities for price_type=configurable (target=service only)"
    )
    form: dict[str, Any] | None = Field(
        default=None, description="Client form values for price_type=custom (target=service only)"
    )
    return_url: str | None = Field(
        default=None,
        description="Return URL if supported (optional)",
    )
    promocode: str | None = Field(
        default=None, max_length=64, description="Discount promo code (target=service only)"
    )

    @model_validator(mode="after")
    def _check_amount(self) -> "PaymentCreate":
        if self.target not in (PayTarget.BALANCE, PayTarget.SERVICE, PayTarget.RENEW, PayTarget.UPGRADE):
            raise ValueError(f"invalid target: {self.target!r}, must be 'balance', 'service', 'renew' or 'upgrade'")
        if self.target == PayTarget.BALANCE:
            if self.amount is None or self.amount <= 0:
                raise ValueError("positive amount is required for target=balance")
            if self.service_id is not None or self.user_svc_id is not None:
                raise ValueError("service_id/user_svc_id must not be supplied for target=balance")
            if self.promocode is not None:
                raise ValueError("promocode is only valid for target=service|renew|upgrade")
            if (
                self.custom_amount is not None
                or self.tier_code is not None
                or self.components is not None
                or self.form is not None
            ):
                raise ValueError(
                    "service options (custom_amount, tier_code, components, form) "
                    "are only valid for target=service|renew|upgrade"
                )
        if self.target == PayTarget.SERVICE:
            if not self.service_id or self.service_id < 1:
                raise ValueError("valid service_id is required for target=service")
            if self.amount is not None:
                raise ValueError(
                    "amount must not be supplied for target=service; "
                    "price is taken from the service or custom_amount"
                )
            if self.amount_in_payment_currency:
                raise ValueError(
                    "amount_in_payment_currency is only valid for target=balance"
                )
        if self.target in (PayTarget.RENEW, PayTarget.UPGRADE):
            if not self.user_svc_id or self.user_svc_id < 1:
                raise ValueError(f"valid user_svc_id is required for target={self.target}")
            if self.amount is not None:
                raise ValueError(
                    f"amount must not be supplied for target={self.target}; price is calculated server-side"
                )
            if self.amount_in_payment_currency:
                raise ValueError(
                    "amount_in_payment_currency is only valid for target=balance"
                )
        return self


class Payment(BaseModel):
    """Public payment."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    provider: str
    amount: Decimal
    currency: str
    base_amount: Decimal | None = None
    base_currency: str | None = None
    fx_rate: Decimal | None = None
    status: str
    target: str
    user_svc_id: int | None = None
    public_data: dict
    payment_url: str | None = None
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
