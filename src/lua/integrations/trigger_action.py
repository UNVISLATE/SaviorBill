"""Действие триггера: исполнение Lua-скрипта.

Lua-реализация `lifecycle.triggers.base.BaseAction` — второе действие,
не зависящее от lua — `lifecycle.triggers.email_action.EmailAction`.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from lifecycle.triggers.base import BaseAction
from lua.bus import LuaBus


class LuaAction(BaseAction):
    """Исполняет скрипт (``config.script_id``), передавая ему контекст события."""

    key = "lua"

    def __init__(self, bus: LuaBus | None, session: AsyncSession) -> None:
        self.bus = bus
        self.s = session

    async def run(self, event: str, ctx: dict, config: dict) -> bool:
        """Запустить Lua-скрипт с контекстом события (event + config + data).

        :arg event: идентификатор доменного события.
        :arg ctx: данные события (передаются скрипту как ``ctx.data``).
        :arg config: ``{script_id}`` (+ произвольная конфигурация действия).
        :return: ``True`` если скрипт исполнен.
        """
        from models.system_scripts import SystemScriptsModel
        from lua.context import LuaRunner

        script_id = config.get("script_id")
        if self.bus is None or not script_id:
            return False

        script = await self.s.get(SystemScriptsModel, int(script_id))
        if script is None or not script.is_active:
            return False

        await LuaRunner(self.bus).run_trigger(script, event, config, ctx)
        return True


__all__ = ["LuaAction"]
