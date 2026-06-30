"""Действие триггера: исполнение Lua-скрипта."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from utils.luabus import LuaBus

from .base import BaseAction


class LuaAction(BaseAction):
    """Исполняет скрипт (``config.script_id``), передавая ему контекст события."""

    key = "lua"

    def __init__(self, bus: LuaBus | None, session: AsyncSession) -> None:
        self.bus = bus
        self.s = session

    async def run(self, ctx: dict, config: dict) -> bool:
        """Запустить Lua-скрипт с контекстом события.

        :arg ctx: контекст события (передаётся в скрипт как ``ctx``).
        :arg config: ``{script_id}``.
        :return: ``True`` если скрипт исполнен.
        """
        from models.system_scripts import SystemScriptsModel

        script_id = config.get("script_id")
        if self.bus is None or not script_id:
            return False

        script = await self.s.get(SystemScriptsModel, int(script_id))
        if script is None or not script.is_active:
            return False

        await self.bus.call("run_script", {"script": script.filename, "ctx": ctx})
        return True


__all__ = ["LuaAction"]
