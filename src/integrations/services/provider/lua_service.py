"""Выдача услуги через Lua-скрипт в LuaWorker."""

from __future__ import annotations

from enums import ScriptKind
from integrations.services.base import BaseIssuer


class LuaService(BaseIssuer):
    """Доставляет услугу, исполняя привязанный к ней Lua-скрипт."""

    async def issue(self, usvc, service, acc) -> None:  # noqa: ANN001 — ORM-объекты
        from models.system_scripts import SystemScriptsModel

        if self.bus is None:
            raise RuntimeError("Lua-выдача недоступна без шины LuaWorker")
        if not service.lua_script_id:
            raise RuntimeError("у услуги не задан Lua-скрипт")

        script = await self.s.get(SystemScriptsModel, service.lua_script_id)
        if script is None or not script.is_active or script.kind != ScriptKind.SERVICE:
            raise RuntimeError("Lua-скрипт услуги недоступен")

        ctx = {
            "user": {
                "id": acc.id,
                "login": acc.login,
                "email": acc.email,
                "service": {
                    "id": usvc.id,
                    "status": usvc.status,
                    "price": str(usvc.price),
                    "params": usvc.params,
                },
                "payment": usvc.payment_id,
            },
            "service": {
                "id": service.id,
                "slug": service.slug,
                "name": service.name,
                "price": str(service.price),
                "params": service.params,
                "settings": service.settings,
            },
        }
        res = await self.bus.call("run_script", {"script": script.filename, "ctx": ctx})
        usvc.public_data = res.get("public") or {}
        usvc.private_data = res.get("private") or {}


__all__ = ["LuaService"]
