"""Контракты заказов (выданных услуг)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class OrderCreate(BaseModel):
    """Create service order."""

    service_id: int = Field(description="Service ID")
    promocode: str | None = Field(
        default=None, max_length=64, description="Discount promo code (optional)"
    )


class Order(BaseModel):
    """Public order."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    service_id: int
    payment_id: int | None = None
    status: str = Field(description="Service status")
    price: Decimal
    discount: Decimal
    public_data: dict
    product_key: str | None = Field(
        default=None,
        description="public_data key for issued product",
    )
    product_kind: str | None = Field(
        default=None,
        description="Product display type",
    )
    actions: list = Field(
        default_factory=list,
        description="Supported service actions",
    )
    expires_at: datetime | None = Field(
        default=None, description="Expiration time; null = no expiry"
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
    """Order with private data."""

    account_id: int
    private_data: dict


class OrderGrant(BaseModel):
    """Grant service manually."""

    account_id: int = Field(description="Recipient account ID")
    service_id: int = Field(description="Service ID")
    params: dict | None = Field(default=None, description="Service params (optional)")
    charge: bool = Field(
        default=False,
        description="Charge user balance (optional)",
    )


__all__ = ["OrderCreate", "Order", "OrderAdmin", "OrderGrant"]
