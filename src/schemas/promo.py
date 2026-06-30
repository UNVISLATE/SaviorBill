"""Контракты промокодов и их каталогов."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from enums import DiscountType, PromoKind


class PromoRedeem(BaseModel):
    """Активация промокода (bonus или service)."""

    code: str = Field(min_length=2, max_length=64)


class PromoResult(BaseModel):
    """Результат активации промокода."""

    kind: str
    message: str
    bonus_added: Decimal | None = None
    order_id: int | None = None


class PromoCatalog(BaseModel):
    """Каталог промокодов (ответ)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    parent_id: int | None = None
    kind: str
    value: Decimal
    discount_type: str
    service_id: int | None = None
    per_user: int
    settings: dict
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
    """Создание каталога промокодов (админ)."""

    name: str = Field(min_length=1, max_length=128)
    slug: str = Field(min_length=2, max_length=64)
    parent_id: int | None = None
    kind: str = PromoKind.BONUS
    value: Decimal = Decimal("0")
    discount_type: str = DiscountType.PERCENT
    service_id: int | None = None
    per_user: int = Field(default=1, ge=1)
    settings: dict = Field(default_factory=dict)
    conditions: dict = Field(default_factory=dict)
    is_active: bool = True


class PromoCatalogPatch(BaseModel):
    """Частичное изменение каталога (только переданные поля)."""

    name: str | None = None
    parent_id: int | None = None
    kind: str | None = None
    value: Decimal | None = None
    discount_type: str | None = None
    service_id: int | None = None
    per_user: int | None = Field(default=None, ge=1)
    settings: dict | None = None
    conditions: dict | None = None
    is_active: bool | None = None


class PromoCode(BaseModel):
    """Промокод (ответ)."""

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
    """Выпуск пачки кодов в каталоге (каталог обязателен)."""

    catalog_id: int
    codes: list[str] | None = Field(
        default=None, description="явные коды; иначе генерируется count штук"
    )
    count: int = Field(default=0, ge=0, le=10_000)
    prefix: str = Field(default="", max_length=16)
    max_uses: int | None = Field(default=None, ge=1)
    valid_to: datetime | None = None


__all__ = [
    "PromoRedeem",
    "PromoResult",
    "PromoCatalog",
    "PromoCatalogCreate",
    "PromoCatalogPatch",
    "PromoCode",
    "PromoCodeBatch",
]
