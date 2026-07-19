"""Lua-адаптеры для доменов lifecycle (delivery/triggers).

Здесь — только "как lua подключается" к абстракциям `lifecycle/*`
(`BaseIssuer`, `BaseAction`), сами абстракции и не-lua реализации
(`KeyService`, `EmailAction`) остаются в `lifecycle/*` — они не зависят от
lua и не должны лежать в этом пакете.
"""

from __future__ import annotations

from lua.integrations.delivery import LuaService
from lua.integrations.trigger_action import LuaAction

__all__ = ["LuaService", "LuaAction"]
