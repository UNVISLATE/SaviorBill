"""Схемы ролей и каталога прав (RBAC, Request/Response)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Role(BaseModel):
    """Роль с деревом прав (ответ)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    title: str | None = None
    is_system: bool
    perms: dict

    @classmethod
    def from_model(cls, m) -> "Role":  # noqa: ANN001 — Role
        """Явное преобразование ORM-роли в схему ответа."""
        return cls.model_validate(m)


class RoleCreate(BaseModel):
    """Создание роли."""

    name: str = Field(
        min_length=2, max_length=64, description="Уникальное имя роли (обязательно)"
    )
    title: str | None = Field(
        default=None, description="Отображаемое название (опционально)"
    )
    perms: dict = Field(
        default_factory=dict, description="Дерево прав роли (опционально)"
    )


class RolePatch(BaseModel):
    """Изменение роли (только переданные поля)."""

    title: str | None = Field(default=None, description="Отображаемое название")
    perms: dict | None = Field(default=None, description="Дерево прав роли")


class PermsCatalog(BaseModel):
    """Каталог прав для назначения ролям."""

    flat: list[str]
    tree: dict


__all__ = ["Role", "RoleCreate", "RolePatch", "PermsCatalog"]
