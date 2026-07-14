"""Схемы ролей и каталога прав (RBAC, Request/Response)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Role(BaseModel):
    """Role with permission tree."""

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
    """Create role."""

    name: str = Field(min_length=2, max_length=64, description="Unique role name")
    title: str | None = Field(default=None, description="Display title (optional)")
    perms: dict = Field(
        default_factory=dict, description="Role permission tree (optional)"
    )


class RolePatch(BaseModel):
    """Update role."""

    title: str | None = Field(default=None, description="Display title")
    perms: dict | None = Field(default=None, description="Role permission tree")


class PermsCatalog(BaseModel):
    """Permission catalog."""

    flat: list[str]
    tree: dict


__all__ = ["Role", "RoleCreate", "RolePatch", "PermsCatalog"]
