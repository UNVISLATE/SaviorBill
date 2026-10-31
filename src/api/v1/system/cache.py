"""API системного мониторинга: статистика и управление кэшем Valkey."""

from __future__ import annotations

from typing import Any
import valkey.asyncio as valkey
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from dependencies.rbac import require_perm, require_any_perm
from dependencies.valkey import get_valkey_client
from services.catalog_cache import flush_cache_data, get_cache_stats

router = APIRouter()


class CacheFlushRequest(BaseModel):
    mode: str = Field(default="catalog", description="'catalog', 'all_cache', or 'reset_stats'")


@router.get(
    "/cache",
    dependencies=[Depends(require_perm("system.cache.read"))],
    summary="Cache statistics and memory usage",
)
async def get_cache_metrics(
    vk: valkey.Valkey = Depends(get_valkey_client),
) -> dict[str, Any]:
    return await get_cache_stats(vk)


@router.post(
    "/cache/flush",
    dependencies=[Depends(require_any_perm("system.cache.manage", "system.cache.edit"))],
    summary="Purge or flush cache namespace",
)
async def flush_cache(
    body: CacheFlushRequest,
    vk: valkey.Valkey = Depends(get_valkey_client),
) -> dict[str, Any]:
    return await flush_cache_data(vk, mode=body.mode)


__all__ = ["router"]
