"""Схемы Lua-скриптов для админ-CRUD (Request/Response).

Отличаются от схем контекста (user/service/payment/…): здесь — регистрация,
замена и выдача метаданных зарегистрированных скриптов.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class LuaScript(BaseModel):
    """Зарегистрированный Lua-скрипт (ответ)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    name: str | None = None
    kind: str
    filename: str
    actions: list = Field(
        default_factory=list,
        description="Поддерживаемые действия скрипта (для payment: create/callback/…)",
    )
    is_active: bool

    @classmethod
    def from_model(cls, m) -> "LuaScript":  # noqa: ANN001 — SystemScriptsModel
        """Явное преобразование ORM-скрипта в схему ответа."""
        return cls.model_validate(m)


class LuaScriptUpload(BaseModel):
    """Регистрация нового Lua-скрипта.

    Имя файла на диске генерируется системой (клиент его не задаёт). ``name`` —
    только для отображения в админке.
    """

    slug: str = Field(
        min_length=2, max_length=64, description="Уникальный slug скрипта (обязательно)"
    )
    name: str | None = Field(
        default=None, max_length=128, description="Отображаемое имя (опционально)"
    )
    kind: str = Field(default="service", description="service | payment | generic")
    actions: list[str] = Field(
        default_factory=list,
        description=(
            "Поддерживаемые действия скрипта. Для payment обязательны "
            "create и callback; для service — минимум create (опционально)"
        ),
    )
    code: str = Field(
        min_length=1,
        max_length=100_000,
        description="Тело Lua-скрипта (модуль с функцией handle(ctx)), обязательно",
    )
    description: str | None = Field(
        default=None, max_length=2048, description="Описание (опционально)"
    )


class LuaScriptPatch(BaseModel):
    """Замена тела существующего Lua-скрипта."""

    code: str = Field(
        min_length=1,
        max_length=100_000,
        description="Новое тело Lua-скрипта (обязательно)",
    )


__all__ = [
    "LuaScript",
    "LuaScriptUpload",
    "LuaScriptPatch",
]
