"""Контракты промокодов и их каталогов."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from enums import PromoKind


def _check_kind_discount(kind: str, discount_type: str | None) -> None:
    """Проверить согласованность ``kind``/``discount_type`` на входе.

    Дублирует :meth:`models.promo_catalogs.PromoCatalogsMngr.
    _validate_kind_discount` — здесь для быстрого отказа на границе API
    (422 вместо похода в БД), там — источник истины для PATCH (учитывает
    уже сохранённое состояние).
    """
    if kind == PromoKind.DISCOUNT and discount_type is None:
        raise ValueError("discount_type is required for kind=discount")
    if kind != PromoKind.DISCOUNT and discount_type is not None:
        raise ValueError("discount_type is only allowed for kind=discount")


class PromoRedeem(BaseModel):
    """Redeem promo code."""

    code: str = Field(min_length=2, max_length=64, description="Promo code")


class PromoResult(BaseModel):
    """Promo redemption result."""

    kind: str
    message: str
    bonus_added: Decimal | None = None
    order_id: int | None = None


class PromoCatalog(BaseModel):
    """Promo catalog."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    kind: str
    value: Decimal
    discount_type: str | None = None
    service_id: int | None = None
    per_user: int | None = None
    conditions: dict
    is_active: bool

    @classmethod
    def from_model(cls, m) -> "PromoCatalog":  # noqa: ANN001 — PromoCatalogsModel
        """Явное преобразование ORM-каталога в схему.

        :arg m: модель каталога.
        :return: схема ответа.
        """
        return cls.model_validate(m)


class PromoCatalogCreate(BaseModel):
    """Create promo catalog."""

    name: str = Field(min_length=1, max_length=128, description="Catalog name")
    slug: str = Field(min_length=2, max_length=64, description="Unique slug")
    kind: str = Field(
        default=PromoKind.BONUS,
        description="Action type: bonus | discount | service",
    )
    value: Decimal = Field(default=Decimal("0"), description="Bonus/discount value")
    discount_type: str | None = Field(
        default=None,
        description="Discount type: percent | fixed",
    )
    service_id: int | None = Field(
        default=None, description="Service ID for kind=service"
    )
    per_user: int | None = Field(
        default=None,
        ge=1,
        description="Redeem limit per user; null = unlimited",
    )
    conditions: dict = Field(
        default_factory=dict, description="Activation conditions (reserved)"
    )
    is_active: bool = Field(default=True, description="Active (optional)")

    @model_validator(mode="after")
    def _validate_kind_discount(self) -> "PromoCatalogCreate":
        _check_kind_discount(self.kind, self.discount_type)
        return self


class PromoCatalogPatch(BaseModel):
    """Update promo catalog."""

    name: str | None = Field(default=None, description="Catalog name")
    kind: str | None = Field(
        default=None, description="Action type: bonus | discount | service"
    )
    value: Decimal | None = Field(default=None, description="Bonus/discount value")
    discount_type: str | None = Field(default=None, description="percent | fixed")
    service_id: int | None = Field(
        default=None, description="Service ID for kind=service"
    )
    per_user: int | None = Field(
        default=None,
        ge=1,
        description="Redeem limit per user; null = unlimited",
    )
    conditions: dict | None = Field(
        default=None, description="Activation conditions (reserved)"
    )
    is_active: bool | None = Field(default=None, description="Active")


class PromoCode(BaseModel):
    """Promo code."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    catalog_id: int
    max_uses: int | None = None
    used_count: int
    valid_to: datetime | None = None
    is_active: bool

    @classmethod
    def from_model(cls, m) -> "PromoCode":  # noqa: ANN001 — PromoCodesModel
        """Явное преобразование ORM-кода в схему.

        :arg m: модель промокода.
        :return: схема ответа.
        """
        return cls.model_validate(m)


class PromoCodeBatch(BaseModel):
    """Create promo code batch."""

    catalog_id: int = Field(description="Promo catalog ID")
    codes: list[str] | None = Field(
        default=None,
        description="Explicit codes; otherwise generate count",
    )
    count: int = Field(
        default=0,
        ge=0,
        le=10_000,
        description="Number of codes to generate",
    )
    prefix: str = Field(
        default="",
        max_length=16,
        description="Generated code prefix",
    )
    max_uses: int | None = Field(
        default=None,
        ge=1,
        description="Activation limit; null = unlimited",
    )
    valid_to: datetime | None = Field(
        default=None, description="Valid until; null = no expiry"
    )


__all__ = [
    "PromoRedeem",
    "PromoResult",
    "PromoCatalog",
    "PromoCatalogCreate",
    "PromoCatalogPatch",
    "PromoCode",
    "PromoCodeBatch",
]
