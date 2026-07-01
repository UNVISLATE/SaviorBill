"""Схема контекста триггерного Lua-скрипта."""

from __future__ import annotations

from pydantic import BaseModel


class LuaTrigger(BaseModel):
    """Контекст действия триггера для Lua.

    :arg event: идентификатор события (см. :class:`integrations.triggers.TriggerEvent`).
    :arg config: полный JSON конфигурации действия триггера (как объект).
    :arg data: унифицированные данные, из-за которых сработал триггер
        (пользователь/услуга/платёж/…), чтобы скрипт мог с ними работать.
    """

    event: str
    config: dict = {}
    data: dict = {}


__all__ = ["LuaTrigger"]
