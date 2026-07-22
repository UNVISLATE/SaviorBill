"""``GET /api/v1/system/stats`` — список инстансов + агрегаты (мониторинг §1).

``system.stats.read`` — список/summary (без деталей текущей джобы конкретного
инстанса); ``system.stats.instance.read`` — детали одного инстанса, включая
какую именно джобу воркер сейчас выполняет (см. ``dependencies/rbac.py``).
"""

from __future__ import annotations

import valkey.asyncio as valkey
from fastapi import APIRouter, Depends, HTTPException, status

from dependencies.rbac import require_perm
from dependencies.valkey import get_valkey_client
from telemetry.instance_metrics import get_instance, list_instances

router = APIRouter()


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


__all__ = ["router"]
