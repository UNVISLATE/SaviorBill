"""Схемы ролей и каталога прав (RBAC, Request/Response)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Role(BaseModel):
    """Role with permission tree."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    key: str | None = None
    title: str | None = None
    is_system: bool
    # Read-only: роль нельзя редактировать/выдавать через API (см. owner_guard).
    is_protected: bool
    admin_login_allowed: bool
    allow_login: bool
    perms: dict

    @classmethod
    def from_model(cls, m) -> "Role":  # noqa: ANN001 — Role
        """Явное преобразование ORM-роли в схему ответа."""
        return cls.model_validate(m)


class RoleCreate(BaseModel):
    """Create role."""

    name: str = Field(min_length=2, max_length=64, description="Unique role name")
    title: str | None = Field(default=None, description="Display title (optional)")
    admin_login_allowed: bool = Field(
        default=False, description="Allow accounts with this role to log into the admin panel"
    )
    allow_login: bool = Field(
        default=True, description="Allow accounts with this role to obtain/refresh tokens at all"
    )
    perms: dict = Field(
        default_factory=dict, description="Role permission tree (optional)"
    )


class RolePatch(BaseModel):
    """Update role."""

    title: str | None = Field(default=None, description="Display title")
    admin_login_allowed: bool | None = Field(
        default=None, description="Allow accounts with this role to log into the admin panel"
    )
    allow_login: bool | None = Field(
        default=None, description="Allow accounts with this role to obtain/refresh tokens at all"
    )
    perms: dict | None = Field(default=None, description="Role permission tree")


class PermsCatalog(BaseModel):
    """Permission catalog."""

    flat: list[str]
    tree: dict


class RoleImpact(BaseModel):
    """Impact summary used before changing or removing a role."""

    role_id: int
    assigned_accounts: int
    is_system: bool
    is_protected: bool
    can_delete: bool


__all__ = ["Role", "RoleCreate", "RolePatch", "PermsCatalog", "RoleImpact"]
