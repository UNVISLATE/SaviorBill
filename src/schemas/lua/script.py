"""Схемы Lua-скриптов для админ-CRUD (Request/Response).

Отличаются от схем контекста (user/service/payment/…): здесь — регистрация,
замена и выдача метаданных зарегистрированных скриптов.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class LuaScript(BaseModel):
    """Registered Lua script."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    name: str | None = None
    kind: str
    filename: str
    actions: list = Field(
        default_factory=list,
        description="Supported script actions",
    )
    settings: dict = Field(
        default_factory=dict,
        description="Shared script settings",
    )
    is_active: bool

    @classmethod
    def from_model(cls, m) -> "LuaScript":  # noqa: ANN001 — SystemScriptsModel
        """Явное преобразование ORM-скрипта в схему ответа."""
        return cls.model_validate(m)


class LuaScriptDetail(LuaScript):
    """Lua script with body."""

    code: str = Field(description="Lua script body")

    @classmethod
    def from_model_with_code(cls, m, code: str) -> "LuaScriptDetail":  # noqa: ANN001
        """Явное преобразование ORM-скрипта + прочитанного тела в схему ответа."""
        return cls(
            id=m.id,
            slug=m.slug,
            name=m.name,
            kind=m.kind,
            filename=m.filename,
            actions=m.actions,
            settings=m.settings,
            is_active=m.is_active,
            code=code,
        )


class LuaScriptUpload(BaseModel):
    """Create Lua script."""

    slug: str = Field(
        min_length=2, max_length=64, description="Unique script slug"
    )
    name: str | None = Field(
        default=None, max_length=128, description="Display name (optional)"
    )
    kind: str = Field(default="service", description="service | payment | generic")
    actions: list[str] = Field(
        default_factory=list,
        description="Supported script actions",
    )
    code: str = Field(
        min_length=1,
        max_length=100_000,
        description="Lua script body",
    )
    settings: dict = Field(
        default_factory=dict,
        description="Shared script settings (optional)",
    )
    description: str | None = Field(
        default=None, max_length=2048, description="Description (optional)"
    )


class LuaScriptPatch(BaseModel):
    """Update Lua script."""

    code: str | None = Field(
        default=None,
        min_length=1,
        max_length=100_000,
        description="New Lua script body (optional)",
    )
    settings: dict | None = Field(
        default=None,
        description="New script settings; replaces all",
    )


__all__ = [
    "LuaScript",
    "LuaScriptDetail",
    "LuaScriptUpload",
    "LuaScriptPatch",
]
