"""Схемы контекста Lua-скриптов.

Из этих схем :mod:`services.lua_ctx` собирает объекты, передаваемые в Lua под
нужным тегом (service/payment/trigger). Финансовые значения сериализуются в
строки (Lua не оперирует Decimal), время — в unix-секунды.

Порядок объявления повторяет порядок сборки контекста для каждого класса
скрипта (см. UPDATE_PLAN.md, «schemas/lua»).
"""

from __future__ import annotations

from .user import LuaUser, LuaUsvc
from .service import LuaService
from .payment import LuaPayment, LuaProvider
from .auth import LuaAuthProvider
from .request import LuaRequest
from .trigger import LuaTrigger
from .script import LuaScript, LuaScriptDetail, LuaScriptUpload, LuaScriptPatch
from .meta import LuaMeta

__all__ = [
    "LuaUser",
    "LuaUsvc",
    "LuaService",
    "LuaPayment",
    "LuaProvider",
    "LuaAuthProvider",
    "LuaRequest",
    "LuaTrigger",
    "LuaScript",
    "LuaScriptDetail",
    "LuaScriptUpload",
    "LuaScriptPatch",
    "LuaMeta",
]
