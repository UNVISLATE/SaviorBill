"""API системного мониторинга: события безопасности и управление блокировками IP."""

from __future__ import annotations

from typing import Any
import valkey.asyncio as valkey
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from dependencies.rbac import require_any_perm, require_perm
from dependencies.valkey import get_valkey_client
from services.security_monitor import ban_ip, list_banned_ips, list_security_events, unban_ip
from utils.request_context import get_current_trace_id

router = APIRouter()


class BanIpRequest(BaseModel):
    ip: str = Field(..., description="IP-адрес для блокировки")
    duration_sec: int = Field(default=900, ge=60, le=86400 * 30, description="Длительность бана в секундах")
    reason: str = Field(default="Ручная блокировка администратором", max_length=255)


@router.get(
    "/security/events",
    dependencies=[Depends(require_any_perm("system.security.read", "settings.security.read"))],
    summary="List security events",
)
async def get_security_events(
    limit: int = Query(default=100, ge=1, le=500),
    ip: str | None = Query(default=None),
    vk: valkey.Valkey = Depends(get_valkey_client),
) -> list[dict[str, Any]]:
    return await list_security_events(vk, limit=limit, ip=ip)


@router.get(
    "/security/banned-ips",
    dependencies=[Depends(require_any_perm("system.security.read", "settings.security.read"))],
    summary="List banned IPs",
)
async def get_banned_ips(
    vk: valkey.Valkey = Depends(get_valkey_client),
) -> list[dict[str, Any]]:
    return await list_banned_ips(vk)


@router.post(
    "/security/banned-ips",
    dependencies=[Depends(require_any_perm("system.security.manage", "settings.security.edit"))],
    summary="Ban an IP address",
)
async def create_banned_ip(
    body: BanIpRequest,
    vk: valkey.Valkey = Depends(get_valkey_client),
) -> dict[str, Any]:
    await ban_ip(
        vk,
        ip=body.ip,
        duration_sec=body.duration_sec,
        reason=body.reason,
        trace_id=get_current_trace_id(),
    )
    return {"ok": True, "ip": body.ip, "duration_sec": body.duration_sec, "reason": body.reason}


@router.delete(
    "/security/banned-ips/{ip}",
    dependencies=[Depends(require_any_perm("system.security.manage", "settings.security.edit"))],
    summary="Unban an IP address",
)
async def remove_banned_ip(
    ip: str,
    vk: valkey.Valkey = Depends(get_valkey_client),
) -> dict[str, Any]:
    unbanned = await unban_ip(vk, ip=ip, trace_id=get_current_trace_id())
    return {"ok": unbanned, "ip": ip}


__all__ = ["router"]
