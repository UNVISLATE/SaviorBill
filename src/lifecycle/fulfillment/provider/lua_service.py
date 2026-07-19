"""Выдача и обслуживание услуги через Lua-скрипт в LuaWorker (action-driven)."""

from __future__ import annotations

from datetime import datetime, timezone

from enums import ScriptKind, ServiceAction, UsvcStatus
from lifecycle.fulfillment.base import BaseIssuer
from lua.context import LuaRunner


class LuaService(BaseIssuer):
    """Исполняет привязанный к услуге Lua-скрипт для действий её ЖЦ.

    Скрипт получает ``ctx.action`` и сам решает, что делать (create/renew/stop/
    delete/freeze). Помимо ``public``/``private`` он может вернуть ``state``
    (новый статус услуги) и ``expires_at`` (unix-время истечения) — их
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

        payment = None
        if usvc.payment_id:
            from models.user_payments import UserPaymentsModel

            payment = await self.s.get(UserPaymentsModel, usvc.payment_id)

        res = await LuaRunner(self.bus).run_service(
            script, action, acc, usvc, service, payment
        )
        usvc.public_data = res.get("public") or {}
        usvc.private_data = res.get("private") or {}

        state = res.get("state")
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
