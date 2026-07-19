"""Схемы услуг каталога (Request/Response)."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from lifecycle.fulfillment import known_delivery_kinds
from schemas.media import Attachment


def _check_delivery(v: str) -> str:
    """Валидировать способ доставки по реестру зарегистрированных issuer'ов.

    Не хардкод-``Enum`` — новый способ доставки добавляется регистрацией
    issuer'а в ``fulfillment/__init__.py`` без правки схем.
    """
    known = known_delivery_kinds()
    if v not in known:
        raise ValueError(
            f"unknown delivery kind: {v!r} (available: {', '.join(known)})"
        )
    return v


class Service(BaseModel):
    """Service in public catalog."""

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
        default_factory=list, description="Product media attachments"
    )
    is_active: bool
    out_of_stock: bool | None = Field(
        default=None,
        description="Out of stock for key delivery; null = lua delivery",
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
    """Service with admin fields."""

    lua_script_id: int | None = None
    params: dict
    settings: dict
    warnings: list[str] = Field(
        default_factory=list,
        description="Non-blocking warnings",
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
    """Create service."""

    slug: str = Field(min_length=2, max_length=64, description="Unique service slug")
    name: str = Field(min_length=1, max_length=128, description="Service name")
    description: str | None = Field(default=None, description="Description (optional)")
    catalog_id: int | None = Field(default=None, description="Catalog ID; null = root")
    price: Decimal = Field(default=Decimal("0"), ge=0, description="Price ≥ 0")
    currency: str = Field(default="RUB", max_length=8, description="Currency")
    delivery: str = Field(default="key", description="Delivery method: key | lua")
    lua_script_id: int | None = Field(
        default=None, description="Lua script ID for delivery=lua"
    )
    params: dict = Field(default_factory=dict, description="Delivery params")
    settings: dict = Field(default_factory=dict, description="Service settings")
    is_active: bool = Field(default=True, description="Active")

    @field_validator("delivery")
    @classmethod
    def _validate_delivery(cls, v: str) -> str:
        return _check_delivery(v)


class ServicePatch(BaseModel):
    """Update service."""

    name: str | None = Field(default=None, description="Service name")
    description: str | None = Field(default=None, description="Description")
    catalog_id: int | None = Field(default=None, description="Catalog ID")
    price: Decimal | None = Field(default=None, description="Price")
    currency: str | None = Field(default=None, description="Currency")
    delivery: str | None = Field(default=None, description="Delivery method: key | lua")
    lua_script_id: int | None = Field(default=None, description="Lua script ID")
    params: dict | None = Field(default=None, description="Delivery params")
    settings: dict | None = Field(default=None, description="Service settings")
    is_active: bool | None = Field(default=None, description="Active")

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
