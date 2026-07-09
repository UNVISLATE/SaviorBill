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
    settings: dict = Field(
        default_factory=dict,
        description="Настройки шаблона (ctx.lua.settings.*), общие для всех услуг/провайдеров скрипта",
    )
    is_active: bool

    @classmethod
    def from_model(cls, m) -> "LuaScript":  # noqa: ANN001 — SystemScriptsModel
        """Явное преобразование ORM-скрипта в схему ответа."""
        return cls.model_validate(m)


class LuaScriptDetail(LuaScript):
    """Зарегистрированный Lua-скрипт с телом (ответ на `GET /lua/{id}`).

    Отдельная схема от списка (`GET /lua`), чтобы список не тянул тела всех
    скриптов из файлов лишний раз — тело читается только при запросе одного.
    """

    code: str = Field(description="Тело Lua-скрипта (модуль с функцией handle(ctx))")

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
    settings: dict = Field(
        default_factory=dict,
        description=(
            "Настройки шаблона (ctx.lua.settings.*): общий JSON, разделяемый всеми "
            "услугами/провайдерами скрипта — напр. учётные данные внешней панели "
            "(опционально)"
        ),
    )
    description: str | None = Field(
        default=None, max_length=2048, description="Описание (опционально)"
    )


class LuaScriptPatch(BaseModel):
    """Обновление существующего Lua-скрипта (передавайте только изменяемые поля)."""

    code: str | None = Field(
        default=None,
        min_length=1,
        max_length=100_000,
        description="Новое тело Lua-скрипта (опционально)",
    )
    settings: dict | None = Field(
        default=None,
        description="Новые настройки шаблона (ctx.lua.settings.*), заменяют целиком (опционально)",
    )


__all__ = [
    "LuaScript",
    "LuaScriptDetail",
    "LuaScriptUpload",
    "LuaScriptPatch",
]
