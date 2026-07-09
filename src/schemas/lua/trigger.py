"""Схема контекста триггерного Lua-скрипта."""

from __future__ import annotations

from pydantic import BaseModel


class LuaTrigger(BaseModel):
    """Trigger action context for Lua."""

    event: str
    config: dict = {}
    data: dict = {}


__all__ = ["LuaTrigger"]
