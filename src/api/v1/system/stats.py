"""``GET /api/v1/system/stats`` — список инстансов + агрегаты (мониторинг §1)."""

from __future__ import annotations

import json
import valkey.asyncio as valkey
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from dependencies.rbac import require_perm
from dependencies.valkey import get_valkey_client
from telemetry.instance_metrics import get_instance, list_instances

router = APIRouter()


class CancelMediaProcessIn(BaseModel):
    token: str | None = Field(default=None, description="Токен задачи конвертации")
    pid: int | None = Field(default=None, description="PID процесса ffmpeg")


@router.get(
    "/stats",
    dependencies=[Depends(require_perm("system.stats.read"))],
    summary="Instance stats",
    description="Все живые инстансы (billing/media/lua) + агрегаты CPU/RSS "
    "по типу сервиса и общий итог. 'online' — жив ли heartbeat-ключ в Valkey "
    "прямо сейчас (TTL не истёк).",
)
async def get_stats(vk: valkey.Valkey = Depends(get_valkey_client)) -> dict:
    return await list_instances(vk)


@router.get(
    "/stats/{service}/{consumer}",
    dependencies=[Depends(require_perm("system.stats.instance.read"))],
    summary="Instance details",
    description="Полная запись heartbeat-хэша одного инстанса; для media, "
    "если сейчас что-то конвертируется — плюс percent/eta_sec текущей джобы.",
)
async def get_stats_instance(
    service: str, consumer: str, vk: valkey.Valkey = Depends(get_valkey_client)
) -> dict:
    instance = await get_instance(vk, service, consumer)
    if instance is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "instance not found")
    return instance


@router.post(
    "/instances/media/cancel",
    dependencies=[Depends(require_perm("system.stats.read"))],
    summary="Cancel media process or job",
    description="Отправить сигнал отмены конкретного FFmpeg-процесса или задачи конвертации.",
)
async def cancel_media_process(
    body: CancelMediaProcessIn,
    vk: valkey.Valkey = Depends(get_valkey_client),
) -> dict:
    if not body.token and not body.pid:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "token or pid required")

    if body.token:
        await vk.set(f"media:cancel:{body.token}", "1", ex=120)
        await vk.hset(
            f"media:status:{body.token}",
            mapping={"state": "cancelled", "error": "Cancelled by administrator"},
        )
    payload = json.dumps({"action": "cancel", "token": body.token, "pid": body.pid})
    await vk.publish("media:control", payload)
    return {"ok": True, "message": "Cancellation signal sent"}


__all__ = ["router"]
