"""Схемы услуг каталога (Request/Response)."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from integrations.services import known_delivery_kinds
from schemas.media import Attachment


def _check_delivery(v: str) -> str:
    """Валидировать способ доставки по реестру зарегистрированных issuer'ов.

    Не хардкод-``Enum`` — новый способ доставки добавляется регистрацией
    issuer'а в ``integrations/services/__init__.py`` без правки схем.
    """
    known = known_delivery_kinds()
    if v not in known:
        raise ValueError(
            f"неизвестный способ доставки: {v!r} (доступны: {', '.join(known)})"
        )
    return v


class Service(BaseModel):
    """Услуга в публичном каталоге (ответ)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    name: str
    description: str | None = None
    catalog_id: int | None = None
    price: Decimal
    currency: str
    delivery: str
    attachments: list[Attachment] = Field(
        default_factory=list, description="Медиа-вложения товара (фото/видео)"
    )
    is_active: bool
    out_of_stock: bool | None = Field(
        default=None,
        description=(
            "Только для delivery=key: закончились ли свободные ключи. "
            "Вычисляется на лету, не хранится в БД. null для delivery=lua."
        ),
    )

    @classmethod
    def from_model(cls, m) -> "Service":  # noqa: ANN001 — ServiceModel
        """Явное преобразование ORM-услуги в публичную схему ответа.

        ``out_of_stock`` не заполняется здесь (требует отдельного запроса к
        пулу ключей) — прокидывается роутером через :meth:`with_stock`.
        """
        return cls(
            id=m.id,
            slug=m.slug,
            name=m.name,
            description=m.description,
            catalog_id=m.catalog_id,
            price=m.price,
            currency=m.currency,
            delivery=m.delivery,
            attachments=[Attachment.from_model(a) for a in m.attachments],
            is_active=m.is_active,
        )

    def with_stock(self, out_of_stock: bool | None) -> "Service":
        """Вернуть копию с проставленным ``out_of_stock`` (для delivery=key)."""
        return self.model_copy(update={"out_of_stock": out_of_stock})


class ServiceAdmin(Service):
    """Услуга с административными полями (ответ)."""

    lua_script_id: int | None = None
    params: dict
    settings: dict
    warnings: list[str] = Field(
        default_factory=list,
        description=(
            "Некритичные предупреждения операции (например, деактивация услуги "
            "с активными выдачами) — не блокируют выполнение."
        ),
    )

    @classmethod
    def from_model(
        cls, m, warnings: list[str] | None = None
    ) -> "ServiceAdmin":  # noqa: ANN001 — ServiceModel
        """Явное преобразование ORM-услуги в админ-схему ответа."""
        return cls(
            id=m.id,
            slug=m.slug,
            name=m.name,
            description=m.description,
            catalog_id=m.catalog_id,
            price=m.price,
            currency=m.currency,
            delivery=m.delivery,
            attachments=[Attachment.from_model(a) for a in m.attachments],
            is_active=m.is_active,
            lua_script_id=m.lua_script_id,
            params=m.params,
            settings=m.settings,
            warnings=warnings or [],
        )


class ServiceCreate(BaseModel):
    """Создание услуги (админ)."""

    slug: str = Field(
        min_length=2, max_length=64, description="Уникальный slug услуги (обязательно)"
    )
    name: str = Field(
        min_length=1, max_length=128, description="Название услуги (обязательно)"
    )
    description: str | None = Field(default=None, description="Описание (опционально)")
    catalog_id: int | None = Field(
        default=None, description="ID каталога; null — корневая (опционально)"
    )
    price: Decimal = Field(
        default=Decimal("0"), ge=0, description="Цена ≥ 0 (опционально)"
    )
    currency: str = Field(
        default="RUB", max_length=8, description="Валюта (опционально)"
    )
    delivery: str = Field(
        default="key", description="Способ выдачи: key | lua (опционально)"
    )
    lua_script_id: int | None = Field(
        default=None, description="ID lua-скрипта для delivery=lua (опционально)"
    )
    params: dict = Field(
        default_factory=dict, description="Параметры выдачи (опционально)"
    )
    settings: dict = Field(
        default_factory=dict, description="Настройки услуги (опционально)"
    )
    is_active: bool = Field(default=True, description="Активна ли услуга (опционально)")

    @field_validator("delivery")
    @classmethod
    def _validate_delivery(cls, v: str) -> str:
        return _check_delivery(v)


class ServicePatch(BaseModel):
    """Частичное изменение услуги (только переданные поля)."""

    name: str | None = Field(default=None, description="Название услуги")
    description: str | None = Field(default=None, description="Описание")
    catalog_id: int | None = Field(default=None, description="ID каталога")
    price: Decimal | None = Field(default=None, description="Цена")
    currency: str | None = Field(default=None, description="Валюта")
    delivery: str | None = Field(default=None, description="Способ выдачи: key | lua")
    lua_script_id: int | None = Field(default=None, description="ID lua-скрипта")
    params: dict | None = Field(default=None, description="Параметры выдачи")
    settings: dict | None = Field(default=None, description="Настройки услуги")
    is_active: bool | None = Field(default=None, description="Активна ли услуга")

    @field_validator("delivery")
    @classmethod
    def _validate_delivery(cls, v: str | None) -> str | None:
        return _check_delivery(v) if v is not None else v


__all__ = [
    "Service",
    "ServiceAdmin",
    "ServiceCreate",
    "ServicePatch",
]
