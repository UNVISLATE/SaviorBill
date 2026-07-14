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
    script_id: int | None = None
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
    secrets: dict = Field(
        default_factory=dict,
        description="Provider secrets JSON (optional)",
    )
    script_id: int | None = Field(
        default=None,
        description=("Unified provider Lua script ID (optional)"),
    )
    extra: dict = Field(
        default_factory=dict, description="Non-secret extra params (optional)"
    )


class PayProviderPatch(BaseModel):
    """Update payment provider."""

    title: str | None = Field(default=None, description="Display name")
    enabled: bool | None = Field(default=None, description="Enabled")
    currency: str | None = Field(default=None, description="Default currency")
    secrets: dict | None = Field(default=None, description="New secrets JSON")
    script_id: int | None = Field(
        default=None, description="Unified provider Lua script ID"
    )
    extra: dict | None = Field(default=None, description="Non-secret extra params")


class PayProviderPublic(BaseModel):
    """Public payment provider."""

    model_config = ConfigDict(from_attributes=True)

    slug: str
    title: str | None = None
    currency: str

    @classmethod
    def from_model(
        cls, m
    ) -> "PayProviderPublic":  # noqa: ANN001 — PaymentProvidersModel
        """Явное преобразование ORM-провайдера в публичную схему."""
        return cls.model_validate(m)


__all__ = [
    "PayProvider",
    "PayProviderCreate",
    "PayProviderPatch",
    "PayProviderPublic",
]
