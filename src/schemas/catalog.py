"""Схемы каталогов услуг (Request/Response)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CatalogResponse(BaseModel):
    """Service catalog."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    parent_id: int | None = None
    description: str | None = None
    icon: str | None = None
    sort: int
    is_active: bool

    @classmethod
    def from_model(cls, m) -> "CatalogResponse":  # noqa: ANN001 — ServiceCatalogsModel
        """Явное преобразование ORM-модели каталога в схему ответа."""
        return cls.model_validate(m)


class CatalogRequest(BaseModel):
    """Create catalog."""

    name: str = Field(min_length=1, max_length=128, description="Catalog name")
    slug: str = Field(min_length=2, max_length=64, description="Unique slug")
    parent_id: int | None = Field(
        default=None,
        description="Parent catalog ID; null = root",
    )
    description: str | None = Field(
        default=None, max_length=512, description="Description (optional)"
    )
    icon: str | None = Field(default=None, description="Icon URL/path (optional)")
    sort: int = Field(default=0, description="Sort order (optional)")
    is_active: bool = Field(default=True, description="Active (optional)")


class CatalogPatch(BaseModel):
    """Update catalog."""

    name: str | None = Field(default=None, description="Catalog name")
    parent_id: int | None = Field(default=None, description="Parent catalog ID")
    description: str | None = Field(default=None, description="Description")
    icon: str | None = Field(default=None, description="Icon URL/path")
    sort: int | None = Field(default=None, description="Sort order")
    is_active: bool | None = Field(default=None, description="Active")


__all__ = [
    "CatalogResponse",
    "CatalogRequest",
    "CatalogPatch",
]
