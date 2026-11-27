"""Контракты заказов (выданных услуг)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class OrderCreate(BaseModel):
    """Create service order."""

    service_id: int = Field(description="Service ID")
    promocode: str | None = Field(
        default=None, max_length=64, description="Discount promo code (optional)"
    )
    custom_amount: Decimal | None = Field(
        default=None, gt=0, description="Arbitrary sum for price_type=custom"
    )
    tier_code: str | None = Field(
        default=None, max_length=64, description="Subtier code for price_type=tiered"
    )
    components: dict[str, Any] | None = Field(
        default=None, description="Component quantities for price_type=configurable"
    )
    form: dict[str, Any] | None = Field(
        default=None, description="Client form values (e.g. steam_login) for price_type=custom"
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
    order_config: dict = Field(
        default_factory=dict,
        description="Snapshot of user selection (tier, components, form)",
    )
    pending_order_config: dict | None = Field(
        default=None,
        description="Scheduled config for next billing period",
    )
    pending_apply_at: datetime | None = Field(
        default=None,
        description="Timestamp when pending_order_config will be applied",
    )
    auto_renew: bool = Field(
        default=False,
        description="Whether automatic balance renewal is enabled",
    )
    auto_renew_last_error: str | None = Field(
        default=None,
        description="Last auto-renewal error if any",
    )
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
    custom_actions: list[dict] = Field(
        default_factory=list,
        description="Custom service actions from catalog service settings",
    )
    allow_early_renew: bool = Field(
        default=False,
        description="Whether early balance renewal is enabled for this service",
    )
    allow_auto_renew: bool = Field(
        default=False,
        description="Whether auto-renewal from balance is enabled for this service",
    )
    allow_renew_config_change: bool = Field(
        default=False,
        description="Whether tier/config change on renewal is enabled",
    )
    allow_instant_upgrade: bool = Field(
        default=False,
        description="Whether instant proration upgrade is enabled",
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
        obj = cls.model_validate(m)
        svc = getattr(m, "service", None)
        if svc is not None and isinstance(getattr(svc, "settings", None), dict):
            raw_ca = svc.settings.get("custom_actions")
            if isinstance(raw_ca, list):
                obj.custom_actions = raw_ca
            obj.allow_early_renew = bool(svc.settings.get("allow_early_renew", False))
            obj.allow_auto_renew = bool(svc.settings.get("allow_auto_renew", False))
            obj.allow_renew_config_change = bool(svc.settings.get("allow_renew_config_change", False))
            obj.allow_instant_upgrade = bool(svc.settings.get("allow_instant_upgrade", False))
        return obj


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
    custom_amount: Decimal | None = Field(
        default=None, gt=0, description="Arbitrary sum for price_type=custom"
    )
    tier_code: str | None = Field(
        default=None, max_length=64, description="Subtier code for price_type=tiered"
    )
    components: dict[str, Any] | None = Field(
        default=None, description="Component quantities for price_type=configurable"
    )
    form: dict[str, Any] | None = Field(
        default=None, description="Client form values"
    )


class OrderActionRequest(BaseModel):
    """Execute action on service order."""

    action: str = Field(
        min_length=1,
        max_length=64,
        description="Action: stop, start, freeze, unfreeze, delete, or custom.<action>",
    )
    verify_code: str | None = Field(
        default=None,
        max_length=32,
        description="Optional 2FA TOTP or emailed verification code for step-up actions",
    )


class OrderActionChallengeRequest(BaseModel):
    """Request an email verification code for a custom service action."""

    action: str = Field(min_length=8, max_length=64, pattern=r"^custom\.[a-z][a-z0-9_]{1,31}$")


class OrderRenewRequest(BaseModel):
    """Renew an existing user service from balance."""

    tier_code: str | None = Field(
        default=None, max_length=64, description="Optional new tier code (when config change on renew is allowed)"
    )
    components: dict[str, Any] | None = Field(
        default=None, description="Optional new components (when config change on renew is allowed)"
    )
    promocode: str | None = Field(
        default=None, max_length=64, description="Optional discount promo code"
    )


class OrderUpgradeRequest(BaseModel):
    """Instant upgrade of an active user service from balance (prorated)."""

    tier_code: str | None = Field(default=None, max_length=64)
    components: dict[str, Any] | None = Field(default=None)
    promocode: str | None = Field(default=None, max_length=64)


class OrderAutoRenewRequest(BaseModel):
    """Toggle auto-renewal from balance for a user service."""

    enabled: bool


__all__ = [
    "OrderCreate",
    "Order",
    "OrderAdmin",
    "OrderGrant",
    "OrderActionRequest",
    "OrderActionChallengeRequest",
    "OrderRenewRequest",
    "OrderUpgradeRequest",
    "OrderAutoRenewRequest",
]
