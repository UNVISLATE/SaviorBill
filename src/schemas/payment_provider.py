"""Схемы платёжных провайдеров (админ, Request/Response)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class PayProvider(BaseModel):
    """Payment provider."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    title: str | None = None
    enabled: bool
    currency: str
    currencies: list[str] = Field(default_factory=list)
    fee_enabled: bool = False
    fee_percent: float = 0.00
    add_fee_to_amount: bool = True
    script_id: int | None = None
    script_version: int | None = None
    extra: dict

    @classmethod
    def from_model(cls, m) -> "PayProvider":  # noqa: ANN001 — PaymentProvidersModel
        """Явное преобразование ORM-провайдера в схему ответа (без секретов)."""
        return cls.model_validate(m)


class PayProviderCreate(BaseModel):
    """Create payment provider."""

    slug: str = Field(
        min_length=2,
        max_length=64,
        description="Unique provider slug",
    )
    title: str | None = Field(default=None, description="Display name (optional)")
    enabled: bool = Field(default=False, description="Enabled (optional)")
    currency: str = Field(
        default="RUB", max_length=8, description="Default currency (optional)"
    )
    currencies: list[str] = Field(
        default_factory=list, description="Supported optional currencies"
    )
    fee_enabled: bool = Field(default=False, description="Enable provider fee accounting")
    fee_percent: float = Field(default=0.00, description="Provider fee percent")
    add_fee_to_amount: bool = Field(default=True, description="Add fee to payment amount for customer")
    secrets: dict = Field(
        default_factory=dict,
        description="Provider secrets JSON (optional)",
    )
    script_id: int | None = Field(
        default=None,
        description=("Unified provider Lua script ID (optional)"),
    )
    script_version: int | None = Field(
        default=None, description="Pinned script version; null = latest"
    )
    extra: dict = Field(
        default_factory=dict, description="Non-secret extra params (optional)"
    )


class PayProviderPatch(BaseModel):
    """Update payment provider."""

    title: str | None = Field(default=None, description="Display name")
    enabled: bool | None = Field(default=None, description="Enabled")
    currency: str | None = Field(default=None, description="Default currency")
    currencies: list[str] | None = Field(
        default=None, description="Supported optional currencies"
    )
    fee_enabled: bool | None = Field(default=None, description="Enable provider fee accounting")
    fee_percent: float | None = Field(default=None, description="Provider fee percent")
    add_fee_to_amount: bool | None = Field(default=None, description="Add fee to payment amount for customer")
    secrets: dict | None = Field(default=None, description="New secrets JSON")
    script_id: int | None = Field(
        default=None, description="Unified provider Lua script ID"
    )
    script_version: int | None = Field(
        default=None, description="Pinned script version; null = latest"
    )
    extra: dict | None = Field(default=None, description="Non-secret extra params")


class PayProviderPublic(BaseModel):
    """Public payment provider."""

    model_config = ConfigDict(from_attributes=True)

    slug: str
    title: str | None = None
    currency: str
    currencies: list[str] = Field(default_factory=list)

    @classmethod
    def from_model(
        cls, m, available_currencies: list[str] | None = None
    ) -> "PayProviderPublic":  # noqa: ANN001 — PaymentProvidersModel
        """Явное преобразование ORM-провайдера в публичную схему с доступными валютами."""
        prov = cls.model_validate(m)
        if available_currencies is not None:
            prov.currencies = available_currencies
        elif not prov.currencies:
            prov.currencies = [prov.currency]
        return prov


__all__ = [
    "PayProvider",
    "PayProviderCreate",
    "PayProviderPatch",
    "PayProviderPublic",
]
