"""Контракты промокодов и их каталогов."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from enums import DiscountType, PromoKind


class PromoRedeem(BaseModel):
    """Активация промокода (bonus или service)."""

    code: str = Field(
        min_length=2, max_length=64, description="Промокод для активации (обязательно)"
    )


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

    name: str = Field(
        min_length=1, max_length=128, description="Имя каталога (обязательно)"
    )
    slug: str = Field(
        min_length=2, max_length=64, description="Уникальный slug (обязательно)"
    )
    parent_id: int | None = Field(
        default=None, description="ID родительского каталога (опционально)"
    )
    kind: str = Field(
        default=PromoKind.BONUS,
        description="Тип действия: bonus | service (опционально)",
    )
    value: Decimal = Field(
        default=Decimal("0"), description="Размер бонуса/скидки (опционально)"
    )
    discount_type: str = Field(
        default=DiscountType.PERCENT, description="percent | fixed (опционально)"
    )
    service_id: int | None = Field(
        default=None, description="ID услуги для kind=service (опционально)"
    )
    per_user: int = Field(
        default=1, ge=1, description="Лимит активаций на пользователя (опционально)"
    )
    settings: dict = Field(
        default_factory=dict, description="Доп-настройки (опционально)"
    )
    conditions: dict = Field(
        default_factory=dict, description="Условия активации (опционально)"
    )
    is_active: bool = Field(
        default=True, description="Активен ли каталог (опционально)"
    )


class PromoCatalogPatch(BaseModel):
    """Частичное изменение каталога (только переданные поля)."""

    name: str | None = Field(default=None, description="Имя каталога")
    parent_id: int | None = Field(default=None, description="ID родительского каталога")
    kind: str | None = Field(default=None, description="Тип действия: bonus | service")
    value: Decimal | None = Field(default=None, description="Размер бонуса/скидки")
    discount_type: str | None = Field(default=None, description="percent | fixed")
    service_id: int | None = Field(
        default=None, description="ID услуги для kind=service"
    )
    per_user: int | None = Field(
        default=None, ge=1, description="Лимит активаций на пользователя"
    )
    settings: dict | None = Field(default=None, description="Доп-настройки")
    conditions: dict | None = Field(default=None, description="Условия активации")
    is_active: bool | None = Field(default=None, description="Активен ли каталог")


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

    catalog_id: int = Field(description="ID каталога промокодов (обязательно)")
    codes: list[str] | None = Field(
        default=None,
        description="Явные коды; если не заданы — генерируется count штук (опционально)",
    )
    count: int = Field(
        default=0,
        ge=0,
        le=10_000,
        description="Сколько кодов сгенерировать (опционально)",
    )
    prefix: str = Field(
        default="",
        max_length=16,
        description="Префикс генерируемых кодов (опционально)",
    )
    max_uses: int | None = Field(
        default=None,
        ge=1,
        description="Лимит активаций кода; null — безлимит (опционально)",
    )
    valid_to: datetime | None = Field(
        default=None, description="Срок действия кодов; null — бессрочно (опционально)"
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
