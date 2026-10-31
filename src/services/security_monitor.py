"""Сервис мониторинга безопасности, подозрительной активности и автоблокировок IP."""

from __future__ import annotations

import json
import logging
from typing import Any
import uuid

import valkey.asyncio as valkey

from models.system_settings import SystemSettingsMngr
from utils.datetime_utils import utc_now
from utils.degrade import VALKEY_ERRORS, note_degraded
from utils.request_context import get_current_trace_id

log = logging.getLogger("saviorbill.security")

KEY_EVENTS_LIST = "system:security_events"
KEY_BANNED_IPS_SET = "security:banned_ips_registry"
PREFIX_BANNED_IP = "security:banned_ips:"
PREFIX_VIOLATIONS = "security:violations:"
MAX_EVENTS_STORED = 1000


async def log_security_event(
    vk: valkey.Valkey,
    *,
    ip: str,
    action: str,
    reason: str,
    scope: str = "default",
    kind: str = "default",
    details: str | None = None,
    user_id: int | None = None,
    user_login: str | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Записать событие безопасности в кольцевой буфер Valkey."""
    event_id = f"sec_ev_{uuid.uuid4().hex[:10]}"
    effective_trace_id = trace_id or get_current_trace_id()
    now_iso = utc_now().isoformat()

    event = {
        "id": event_id,
        "trace_id": effective_trace_id,
        "timestamp": now_iso,
        "ip": ip,
        "scope": scope,
        "kind": kind,
        "action": action,
        "reason": reason,
        "details": details or "",
        "user_id": user_id,
        "user_login": user_login,
    }

    try:
        raw = json.dumps(event)
        await vk.lpush(KEY_EVENTS_LIST, raw)
        await vk.ltrim(KEY_EVENTS_LIST, 0, MAX_EVENTS_STORED - 1)
        log.warning(
            "security event [%s] action=%s ip=%s reason=%s trace_id=%s",
            event_id,
            action,
            ip,
            reason,
            effective_trace_id,
        )
    except VALKEY_ERRORS as exc:
        note_degraded("security", exc)

    return event


async def is_ip_banned(vk: valkey.Valkey, ip: str) -> tuple[bool, str | None, int | None]:
    """Проверить, заблокирован ли IP.

    Возвращает (is_banned, reason, ttl_remaining_sec).
    """
    try:
        raw = await vk.get(f"{PREFIX_BANNED_IP}{ip}")
        if raw is not None:
            ttl = await vk.ttl(f"{PREFIX_BANNED_IP}{ip}")
            try:
                data = json.loads(raw)
                reason = data.get("reason", "Suspicious activity")
            except Exception:
                reason = str(raw)
            return True, reason, ttl if ttl > 0 else None
        return False, None, None
    except VALKEY_ERRORS as exc:
        note_degraded("security", exc)
        return False, None, None


async def ban_ip(
    vk: valkey.Valkey,
    ip: str,
    duration_sec: int = 900,
    reason: str = "Manual admin block",
    trace_id: str | None = None,
) -> None:
    """Заблокировать IP на duration_sec секунд."""
    try:
        data = {
            "ip": ip,
            "banned_at": utc_now().isoformat(),
            "reason": reason,
            "duration_sec": duration_sec,
        }
        await vk.set(f"{PREFIX_BANNED_IP}{ip}", json.dumps(data), ex=duration_sec)
        await vk.sadd(KEY_BANNED_IPS_SET, ip)
        await log_security_event(
            vk,
            ip=ip,
            action="ip_banned",
            reason=reason,
            details=f"IP заблокирован на {duration_sec} сек.",
            trace_id=trace_id,
        )
    except VALKEY_ERRORS as exc:
        note_degraded("security", exc)


async def unban_ip(
    vk: valkey.Valkey,
    ip: str,
    trace_id: str | None = None,
) -> bool:
    """Разблокировать IP."""
    try:
        deleted = await vk.delete(f"{PREFIX_BANNED_IP}{ip}")
        await vk.srem(KEY_BANNED_IPS_SET, ip)
        await vk.delete(f"{PREFIX_VIOLATIONS}{ip}")
        if deleted:
            await log_security_event(
                vk,
                ip=ip,
                action="ip_unbanned",
                reason="Unbanned by admin",
                trace_id=trace_id,
            )
            return True
        return False
    except VALKEY_ERRORS as exc:
        note_degraded("security", exc)
        return False


async def check_and_apply_autoban(
    vk: valkey.Valkey,
    ip: str,
    settings: SystemSettingsMngr,
    trace_id: str | None = None,
) -> bool:
    """Зафиксировать нарушение и при превышении порога активировать Auto-Ban.

    Возвращает True, если в результате проверки IP был забанен.
    """
    try:
        enabled_raw = await settings.get("security.autoban.enabled", "1")
        enabled = enabled_raw.strip().lower() in ("1", "true", "yes", "on")
        if not enabled:
            return False

        threshold_raw = await settings.get("security.autoban.threshold", "5")
        window_raw = await settings.get("security.autoban.window_sec", "60")
        duration_raw = await settings.get("security.autoban.duration_sec", "900")

        threshold = int(threshold_raw)
        window_sec = int(window_raw)
        duration_sec = int(duration_raw)

        v_key = f"{PREFIX_VIOLATIONS}{ip}"
        count = await vk.incr(v_key)
        if count == 1:
            await vk.expire(v_key, window_sec)

        if count >= threshold:
            reason = f"Превышен порог нарушений: {count} за {window_sec}с (Auto-Ban)"
            await ban_ip(vk, ip, duration_sec=duration_sec, reason=reason, trace_id=trace_id)
            return True

        return False
    except VALKEY_ERRORS as exc:
        note_degraded("security", exc)
        return False


async def list_security_events(
    vk: valkey.Valkey, limit: int = 100, ip: str | None = None
) -> list[dict[str, Any]]:
    """Получить список последних событий безопасности."""
    events: list[dict[str, Any]] = []
    try:
        raw_items = await vk.lrange(KEY_EVENTS_LIST, 0, min(limit * 2, MAX_EVENTS_STORED) - 1)
        for item in raw_items:
            try:
                ev = json.loads(item)
                if "trace_id" not in ev and "ray_id" in ev:
                    ev["trace_id"] = ev["ray_id"]
                if ip and ev.get("ip") != ip:
                    continue
                events.append(ev)
                if len(events) >= limit:
                    break
            except Exception:
                continue
    except VALKEY_ERRORS as exc:
        note_degraded("security", exc)
    return events


async def list_banned_ips(vk: valkey.Valkey) -> list[dict[str, Any]]:
    """Получить список всех активно заблокированных IP с оставшимся TTL."""
    result: list[dict[str, Any]] = []
    try:
        all_ips = await vk.smembers(KEY_BANNED_IPS_SET)
        stale_ips: list[str] = []

        for item in all_ips:
            ip = item if isinstance(item, str) else item.decode()
            raw = await vk.get(f"{PREFIX_BANNED_IP}{ip}")
            if raw is None:
                stale_ips.append(ip)
                continue
            ttl = await vk.ttl(f"{PREFIX_BANNED_IP}{ip}")
            try:
                data = json.loads(raw)
            except Exception:
                data = {"ip": ip, "reason": str(raw)}
            data["ttl_remaining_sec"] = ttl if ttl > 0 else 0
            result.append(data)

        if stale_ips:
            await vk.srem(KEY_BANNED_IPS_SET, *stale_ips)

    except VALKEY_ERRORS as exc:
        note_degraded("security", exc)
    return result


__all__ = [
    "log_security_event",
    "is_ip_banned",
    "ban_ip",
    "unban_ip",
    "check_and_apply_autoban",
    "list_security_events",
    "list_banned_ips",
]
