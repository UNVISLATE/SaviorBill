"""Выдача и обслуживание услуги через Lua-скрипт в LuaWorker (action-driven)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from enums import ScriptKind, ServiceAction, UsvcStatus
from lifecycle.delivery.base import BaseIssuer
from lua.context import LuaRunner
from utils.datetime_utils import utc_now

_POLL_MIN_INTERVAL = 5
_POLL_MAX_INTERVAL = 300
_POLL_DEFAULT_INTERVAL = 15
_POLL_MAX_ATTEMPTS = 60
_POLL_DEFAULT_ATTEMPTS = 20
_POLL_MAX_TTL_SEC = 7200


def _clamp_poll_config(raw_poll: dict | None, prev: dict | None = None) -> dict:
    """Нормализовать и ограничить параметры поллинга из Lua-скрипта."""
    raw = raw_poll if isinstance(raw_poll, dict) else {}
    prev_cfg = prev if isinstance(prev, dict) else {}

    action = str(raw.get("action") or prev_cfg.get("action") or ServiceAction.POLL).strip() or ServiceAction.POLL
    try:
        interval = int(raw.get("interval_sec", prev_cfg.get("interval_sec", _POLL_DEFAULT_INTERVAL)))
    except (TypeError, ValueError):
        interval = _POLL_DEFAULT_INTERVAL
    interval = max(_POLL_MIN_INTERVAL, min(interval, _POLL_MAX_INTERVAL))

    try:
        max_attempts = int(raw.get("max_attempts", prev_cfg.get("max_attempts", _POLL_DEFAULT_ATTEMPTS)))
    except (TypeError, ValueError):
        max_attempts = _POLL_DEFAULT_ATTEMPTS
    max_attempts = max(1, min(max_attempts, _POLL_MAX_ATTEMPTS))

    backoff = str(raw.get("backoff") or prev_cfg.get("backoff") or "fixed").strip().lower()
    if backoff not in ("fixed", "exponential"):
        backoff = "fixed"

    attempts = int(prev_cfg.get("attempts", 0))
    deadline_at = prev_cfg.get("deadline_at")
    if not deadline_at:
        ttl = min(max_attempts * interval * 2, _POLL_MAX_TTL_SEC)
        ttl = max(ttl, interval * 2)
        deadline_at = (utc_now() + timedelta(seconds=ttl)).isoformat()

    return {
        "action": action,
        "interval_sec": interval,
        "max_attempts": max_attempts,
        "backoff": backoff,
        "attempts": attempts,
        "deadline_at": deadline_at,
    }


class LuaService(BaseIssuer):
    """Исполняет привязанный к услуге Lua-скрипт для действий её ЖЦ."""

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
        from models.system_scripts import SystemScriptsModel, resolve_version

        if self.bus is None:
            raise RuntimeError("Lua-выдача недоступна без шины LuaWorker")
        if not service.lua_script_id:
            raise RuntimeError("у услуги не задан Lua-скрипт")

        script = await self.s.get(SystemScriptsModel, service.lua_script_id)
        if script is None or not script.is_active or script.kind != ScriptKind.SERVICE:
            raise RuntimeError("Lua-скрипт услуги недоступен")
        filename, resolved_version = await resolve_version(
            self.s, script, service.lua_script_version
        )

        payment = None
        if usvc.payment_id:
            from models.user_payments import UserPaymentsModel

            payment = await self.s.get(UserPaymentsModel, usvc.payment_id)

        res = await LuaRunner(self.bus).run_service(
            script,
            action,
            acc,
            usvc,
            service,
            payment,
            filename=filename,
            version=resolved_version,
            requested_version=service.lua_script_version,
        )
        if res.get("ok") is False:
            raise RuntimeError(str(res.get("error") or f"lua action '{action}' returned ok=false"))
        priv_merged = {**(usvc.private_data or {}), **(res.get("private") or {})}
        usvc.public_data = {**(usvc.public_data or {}), **(res.get("public") or {})}
        # Провенанс: какая именно версия скрипта реально выполнила это
        # действие (пин на услуге мог измениться/сброситься между выдачами).
        usvc.lua_script_version = resolved_version

        state = res.get("state") or res.get("status")
        if state == UsvcStatus.PROVISIONING:
            usvc.status = UsvcStatus.PROVISIONING
            priv_merged["_provisioning"] = _clamp_poll_config(
                res.get("poll"), priv_merged.get("_provisioning")
            )
        else:
            priv_merged.pop("_provisioning", None)
            if state:
                usvc.status = state
            elif action in (ServiceAction.STOP, ServiceAction.DELETE):
                usvc.status = UsvcStatus.STOPPED
            elif action == ServiceAction.FREEZE:
                usvc.status = UsvcStatus.FROZEN
            elif action in (ServiceAction.START, ServiceAction.UNFREEZE, ServiceAction.POLL):
                usvc.status = UsvcStatus.ACTIVE

        usvc.private_data = priv_merged

        expires_at = res.get("expires_at")
        if expires_at is not None:
            usvc.expires_at = datetime.fromtimestamp(int(expires_at), tz=timezone.utc)


__all__ = ["LuaService"]
