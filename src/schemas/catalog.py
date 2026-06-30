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

    name: str = Field(
        min_length=1, max_length=128, description="Имя каталога (обязательно)"
    )
    slug: str = Field(
        min_length=2, max_length=64, description="Уникальный slug (обязательно)"
    )
    parent_id: int | None = Field(
        default=None,
        description="ID родительского каталога; null — корневой (опционально)",
    )
    description: str | None = Field(
        default=None, max_length=512, description="Описание (опционально)"
    )
    icon: str | None = Field(default=None, description="URL/путь иконки (опционально)")
    sort: int = Field(default=0, description="Порядок сортировки (опционально)")
    is_active: bool = Field(
        default=True, description="Активен ли каталог (опционально)"
    )


class CatalogPatch(BaseModel):
    """Частичное изменение каталога (только переданные поля)."""

    name: str | None = Field(default=None, description="Имя каталога")
    parent_id: int | None = Field(default=None, description="ID родительского каталога")
    description: str | None = Field(default=None, description="Описание")
    icon: str | None = Field(default=None, description="URL/путь иконки")
    sort: int | None = Field(default=None, description="Порядок сортировки")
    is_active: bool | None = Field(default=None, description="Активен ли каталог")


__all__ = [
    "CatalogResponse",
    "CatalogRequest",
    "CatalogPatch",
]
