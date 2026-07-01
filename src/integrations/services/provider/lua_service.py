"""Выдача и обслуживание услуги через Lua-скрипт в LuaWorker (action-driven)."""

from __future__ import annotations

from datetime import datetime, timezone

from enums import ScriptKind, ServiceAction, UsvcStatus
from integrations.services.base import BaseIssuer


class LuaService(BaseIssuer):
    """Исполняет привязанный к услуге Lua-скрипт для действий её ЖЦ.

    Скрипт получает ``ctx.action`` и сам решает, что делать (create/renew/stop/
    delete/freeze). Помимо ``public``/``private`` он может вернуть ``state``
    (новое состояние услуги) и ``expires_at`` (unix-время истечения) — их
    подхватывает billing-loop для планирования.
    """

    async def issue(self, usvc, service, acc) -> None:  # noqa: ANN001 — ORM-объекты
        """Первичная выдача услуги (действие ``create``)."""
        await self.run_action(usvc, service, acc, ServiceAction.CREATE)

    async def run_action(self, usvc, service, acc, action) -> None:  # noqa: ANN001
        """Выполнить действие ЖЦ услуги через lua-скрипт.

        :arg usvc: выданная услуга (ORM).
        :arg service: эталонная услуга (ORM).
        :arg acc: аккаунт-владелец (ORM).
        :arg action: действие из :class:`enums.ServiceAction`.
        """
        from models.system_scripts import SystemScriptsModel

        if self.bus is None:
            raise RuntimeError("Lua-выдача недоступна без шины LuaWorker")
        if not service.lua_script_id:
            raise RuntimeError("у услуги не задан Lua-скрипт")

        script = await self.s.get(SystemScriptsModel, service.lua_script_id)
        if script is None or not script.is_active or script.kind != ScriptKind.SERVICE:
            raise RuntimeError("Lua-скрипт услуги недоступен")

        ctx = {
            "action": action,
            "user": {
                "id": acc.id,
                "login": acc.login,
                "email": acc.email,
                "service": {
                    "id": usvc.id,
                    "status": usvc.status,
                    "price": str(usvc.price),
                    "duration": usvc.duration,
                    "params": getattr(usvc, "order_params", {}) or {},
                },
                "payment": usvc.payment_id,
            },
            "service": {
                "id": service.id,
                "slug": service.slug,
                "name": service.name,
                "price": str(service.price),
                "duration": service.duration,
                "params": service.params,
                "settings": service.settings,
                "actions": service.actions,
            },
        }
        res = await self.bus.call("run_script", {"script": script.filename, "ctx": ctx})
        usvc.public_data = res.get("public") or {}
        usvc.private_data = res.get("private") or {}

        state = res.get("state") or res.get("status")
        if state:
            usvc.status = state
        elif action in (ServiceAction.STOP, ServiceAction.DELETE):
            usvc.status = UsvcStatus.STOPPED
        elif action == ServiceAction.FREEZE:
            usvc.status = UsvcStatus.FROZEN

        expires_at = res.get("expires_at")
        if expires_at is not None:
            usvc.expires_at = datetime.fromtimestamp(int(expires_at), tz=timezone.utc)


__all__ = ["LuaService"]
