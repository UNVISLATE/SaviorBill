"""Схемы каталогов услуг (Request/Response)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CatalogResponse(BaseModel):
    """Каталог услуг (ответ)."""

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
    """Создание каталога (админ)."""

    name: str = Field(min_length=1, max_length=128)
    slug: str = Field(min_length=2, max_length=64)
    parent_id: int | None = None
    description: str | None = Field(default=None, max_length=512)
    icon: str | None = None
    sort: int = 0
    is_active: bool = True


class CatalogPatch(BaseModel):
    """Частичное изменение каталога (только переданные поля)."""

    name: str | None = None
    parent_id: int | None = None
    description: str | None = None
    icon: str | None = None
    sort: int | None = None
    is_active: bool | None = None


__all__ = [
    "CatalogResponse",
    "CatalogRequest",
    "CatalogPatch",
]
