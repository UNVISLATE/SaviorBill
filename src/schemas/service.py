"""Схемы услуг каталога (Request/Response)."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from enums import PriceType
from lifecycle.delivery import known_delivery_kinds
from schemas.media import Attachment
from schemas.promo import PromoQuote


class CustomFormField(BaseModel):
    """Field configuration for client order forms (e.g. Steam login)."""

    key: str = Field(min_length=1, max_length=64, description="Field key identifier")
    label: str = Field(min_length=1, max_length=128, description="Field display label")
    type: str = Field(default="text", description="Input type: text | number | email")
    required: bool = Field(default=True, description="Whether field is required")
    placeholder: str | None = Field(default=None, max_length=128)
    regex: str | None = Field(default=None, max_length=256, description="Validation regex pattern")
    regex_error: str | None = Field(default=None, max_length=256, description="Error message if regex fails")


class CustomPricingConfig(BaseModel):
    """Configuration for custom amount services (Steam top-ups, donations)."""

    min: Decimal = Field(gt=0, description="Minimum allowed amount")
    max: Decimal = Field(gt=0, description="Maximum allowed amount")
    step: Decimal | None = Field(default=None, gt=0, description="Amount step (multiple)")
    form: list[CustomFormField] = Field(default_factory=list, description="Client form fields")
    manifest: dict | None = Field(default=None, description="SDUI manifest (client_order_form, layout)")

    @model_validator(mode="after")
    def _check_bounds(self) -> "CustomPricingConfig":
        if self.min > self.max:
            raise ValueError(f"min ({self.min}) cannot be greater than max ({self.max})")
        return self


class TierPlan(BaseModel):
    """Single tariff plan (e.g. 1 Month, Pro, or 1 Month Basic)."""

    code: str = Field(min_length=1, max_length=64, description="Unique plan code")
    title: str = Field(min_length=1, max_length=128, description="Plan title")
    price: Decimal = Field(ge=0, description="Price for this plan")
    duration_days: int | None = Field(default=None, ge=1, description="Duration in days (legacy)")
    duration_seconds: int | None = Field(default=None, ge=1, description="Duration in seconds (null = no expiry / service duration)")
    group: str | None = Field(default=None, max_length=64, description="Optional category or group name")
    settings_override: dict = Field(default_factory=dict, description="Override for ctx.service.settings")


TierSubtier = TierPlan


class TierGroup(BaseModel):
    """Legacy/structured group of plans (e.g. 1 Month, 1 Year)."""

    code: str = Field(min_length=1, max_length=64, description="Tier group code")
    title: str = Field(min_length=1, max_length=128, description="Tier group title")
    subtiers: list[TierPlan] = Field(default_factory=list, description="Subtiers")


class TieredPricingConfig(BaseModel):
    """Configuration for tiered subscription/pricing services."""

    tiers: list[TierPlan | TierGroup] = Field(default_factory=list, description="List of plans or plan groups")
    form: list[CustomFormField] = Field(default_factory=list, description="Client form fields")
    manifest: dict | None = Field(default=None, description="SDUI manifest (client_order_form, layout)")


class ComponentOption(BaseModel):
    """Dropdown/select option for a configurable component."""

    value: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=128)
    price_delta: Decimal = Field(default=Decimal("0"), description="Price delta for this option")


class ConfigurableComponent(BaseModel):
    """Single resource/component in a configurable service (vCPU, RAM, SSD)."""

    code: str = Field(min_length=1, max_length=64, description="Component unique code")
    name: str = Field(min_length=1, max_length=128, description="Component name")
    type: str = Field(default="slider", description="UI control type: slider | select | switch | stepper")
    unit: str = Field(default="", max_length=32, description="Unit of measurement (e.g. GB, vCPU)")
    unit_price: Decimal = Field(default=Decimal("0"), ge=0, description="Price per unit")
    min: Decimal | None = Field(default=None, description="Minimum quantity")
    max: Decimal | None = Field(default=None, description="Maximum quantity")
    step: Decimal | None = Field(default=None, gt=0, description="Step quantity")
    default: str | Decimal | int = Field(default="0", description="Default value")
    path: str = Field(min_length=1, max_length=128, description="Target dot-path in ctx.service.settings")
    options: list[ComponentOption] | None = Field(default=None, description="Options if type == 'select'")


class ConfigurablePricingConfig(BaseModel):
    """Configuration for configurable calculator services."""

    components: list[ConfigurableComponent] = Field(default_factory=list, description="Components")
    form: list[CustomFormField] = Field(default_factory=list, description="Client form fields")
    manifest: dict | None = Field(default=None, description="SDUI manifest (client_order_form, layout)")


def validate_pricing_config(price_type: str, config: dict | None) -> dict:
    """Validate pricing_config according to price_type and return dumped json dict."""
    if config is None:
        config = {}
    if price_type == PriceType.FIXED:
        return config
    elif price_type == PriceType.CUSTOM:
        return CustomPricingConfig.model_validate(config).model_dump(mode="json")
    elif price_type == PriceType.TIERED:
        return TieredPricingConfig.model_validate(config).model_dump(mode="json")
    elif price_type == PriceType.CONFIGURABLE:
        return ConfigurablePricingConfig.model_validate(config).model_dump(mode="json")
    else:
        raise ValueError(f"unknown price_type: {price_type!r}")


def _check_delivery(v: str) -> str:
    """Валидировать способ доставки по реестру зарегистрированных issuer'ов.

    Не хардкод-``Enum`` — новый способ доставки добавляется регистрацией
    issuer'а в ``lifecycle/delivery/__init__.py`` без правки схем.
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
    price_type: str = PriceType.FIXED
    pricing_config: dict = Field(default_factory=dict)
    delivery: str
    attachments: list[Attachment] = Field(
        default_factory=list, description="Product media attachments"
    )
    is_active: bool
    is_recommended: bool = False
    out_of_stock: bool | None = Field(
        default=None,
        description="Out of stock for key delivery; null = lua delivery",
    )
    promo_quote: PromoQuote | None = Field(
        default=None,
        description="Discount preview for ?promo=CODE; null if not requested",
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
            price_type=getattr(m, "price_type", PriceType.FIXED),
            pricing_config=getattr(m, "pricing_config", {}) or {},
            delivery=m.delivery,
            attachments=[Attachment.from_model(a) for a in m.attachments],
            is_active=m.is_active,
            is_recommended=bool((getattr(m, "settings", {}) or {}).get("is_recommended", False)),
        )

    def with_stock(self, out_of_stock: bool | None) -> "Service":
        """Вернуть копию с проставленным ``out_of_stock`` (для delivery=key)."""
        return self.model_copy(update={"out_of_stock": out_of_stock})

    def with_promo_quote(self, quote: PromoQuote | None) -> "Service":
        """Вернуть копию с проставленным превью скидки (для ``?promo=CODE``)."""
        return self.model_copy(update={"promo_quote": quote})


class ServiceAdmin(Service):
    """Service with admin fields."""

    lua_script_id: int | None = None
    lua_script_version: int | None = None
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
            price_type=getattr(m, "price_type", PriceType.FIXED),
            pricing_config=getattr(m, "pricing_config", {}) or {},
            delivery=m.delivery,
            attachments=[Attachment.from_model(a) for a in m.attachments],
            is_active=m.is_active,
            lua_script_id=m.lua_script_id,
            lua_script_version=m.lua_script_version,
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
    price_type: str = Field(
        default=PriceType.FIXED,
        max_length=16,
        description="Pricing type: fixed | custom | tiered | configurable",
    )
    pricing_config: dict = Field(
        default_factory=dict,
        description="Pricing configuration (schema depends on price_type)",
    )
    delivery: str = Field(default="key", description="Delivery method: key | lua")
    lua_script_id: int | None = Field(
        default=None, description="Lua script ID for delivery=lua"
    )
    lua_script_version: int | None = Field(
        default=None, description="Pinned script version; null = latest"
    )
    params: dict = Field(default_factory=dict, description="Delivery params")
    settings: dict = Field(default_factory=dict, description="Service settings")
    is_active: bool = Field(default=True, description="Active")

    @field_validator("delivery")
    @classmethod
    def _validate_delivery(cls, v: str) -> str:
        return _check_delivery(v)

    @model_validator(mode="after")
    def _validate_pricing(self) -> "ServiceCreate":
        if self.price_type not in PriceType.ALL:
            raise ValueError(
                f"unknown price_type: {self.price_type!r} (available: {', '.join(PriceType.ALL)})"
            )
        if self.delivery == "key" and self.price_type != PriceType.FIXED:
            raise ValueError("delivery 'key' is only supported for price_type='fixed'")
        self.pricing_config = validate_pricing_config(self.price_type, self.pricing_config)
        return self


class ServicePatch(BaseModel):
    """Update service."""

    name: str | None = Field(default=None, description="Service name")
    description: str | None = Field(default=None, description="Description")
    catalog_id: int | None = Field(default=None, description="Catalog ID")
    price: Decimal | None = Field(default=None, description="Price")
    currency: str | None = Field(default=None, description="Currency")
    price_type: str | None = Field(default=None, description="Pricing type")
    pricing_config: dict | None = Field(default=None, description="Pricing configuration")
    delivery: str | None = Field(default=None, description="Delivery method: key | lua")
    lua_script_id: int | None = Field(default=None, description="Lua script ID")
    lua_script_version: int | None = Field(
        default=None, description="Pinned script version; null = latest"
    )
    params: dict | None = Field(default=None, description="Delivery params")
    settings: dict | None = Field(default=None, description="Service settings")
    is_active: bool | None = Field(default=None, description="Active")

    @field_validator("delivery")
    @classmethod
    def _validate_delivery(cls, v: str | None) -> str | None:
        return _check_delivery(v) if v is not None else v

    @model_validator(mode="after")
    def _validate_pricing(self) -> "ServicePatch":
        if self.price_type is not None and self.price_type not in PriceType.ALL:
            raise ValueError(
                f"unknown price_type: {self.price_type!r} (available: {', '.join(PriceType.ALL)})"
            )
        if self.delivery == "key" and self.price_type is not None and self.price_type != PriceType.FIXED:
            raise ValueError("delivery 'key' is only supported for price_type='fixed'")
        if self.price_type is not None and self.pricing_config is not None:
            self.pricing_config = validate_pricing_config(self.price_type, self.pricing_config)
        return self


__all__ = [
    "CustomFormField",
    "CustomPricingConfig",
    "TierSubtier",
    "TierGroup",
    "TieredPricingConfig",
    "ComponentOption",
    "ConfigurableComponent",
    "ConfigurablePricingConfig",
    "validate_pricing_config",
    "Service",
    "ServiceAdmin",
    "ServiceCreate",
    "ServicePatch",
]
