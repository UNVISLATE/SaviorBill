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
        raise ValueError("для kind=discount обязателен discount_type")
    if kind != PromoKind.DISCOUNT and discount_type is not None:
        raise ValueError("discount_type допустим только при kind=discount")


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
    """Создание каталога промокодов (админ)."""

    name: str = Field(
        min_length=1, max_length=128, description="Имя каталога (обязательно)"
    )
    slug: str = Field(
        min_length=2, max_length=64, description="Уникальный slug (обязательно)"
    )
    kind: str = Field(
        default=PromoKind.BONUS,
        description="Тип действия: bonus | discount | service (опционально)",
    )
    value: Decimal = Field(
        default=Decimal("0"), description="Размер бонуса/скидки (опционально)"
    )
    discount_type: str | None = Field(
        default=None,
        description=(
            "percent | fixed — обязателен при kind=discount, для остальных "
            "kind указывать нельзя (опционально)"
        ),
    )
    service_id: int | None = Field(
        default=None, description="ID услуги для kind=service (опционально)"
    )
    per_user: int | None = Field(
        default=None,
        ge=1,
        description=(
            "Лимит на количество РАЗНЫХ кодов каталога, которые может "
            "погасить один пользователь; null — без лимита (опционально). "
            "0 и отрицательные значения запрещены."
        ),
    )
    conditions: dict = Field(
        default_factory=dict, description="Условия активации, зарезервировано (опционально)"
    )
    is_active: bool = Field(
        default=True, description="Активен ли каталог (опционально)"
    )

    @model_validator(mode="after")
    def _validate_kind_discount(self) -> "PromoCatalogCreate":
        _check_kind_discount(self.kind, self.discount_type)
        return self


class PromoCatalogPatch(BaseModel):
    """Частичное изменение каталога (только переданные поля).

    Согласованность ``kind``/``discount_type`` при частичном обновлении
    проверяется не здесь (схема не знает текущее состояние строки), а в
    :meth:`models.promo_catalogs.PromoCatalogsMngr.update` — по итоговому
    состоянию (старое значение + патч).
    """

    name: str | None = Field(default=None, description="Имя каталога")
    kind: str | None = Field(
        default=None, description="Тип действия: bonus | discount | service"
    )
    value: Decimal | None = Field(default=None, description="Размер бонуса/скидки")
    discount_type: str | None = Field(default=None, description="percent | fixed")
    service_id: int | None = Field(
        default=None, description="ID услуги для kind=service"
    )
    per_user: int | None = Field(
        default=None,
        ge=1,
        description=(
            "Лимит на количество РАЗНЫХ кодов каталога на пользователя; "
            "null — без лимита. 0 и отрицательные значения запрещены."
        ),
    )
    conditions: dict | None = Field(
        default=None, description="Условия активации, зарезервировано"
    )
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
