"""API системного мониторинга: журнал ошибок HTTP 4xx и 5xx."""

from __future__ import annotations

from typing import Any
import valkey.asyncio as valkey
from fastapi import APIRouter, Depends, Query

from dependencies.rbac import require_perm
from dependencies.valkey import get_valkey_client
from services.error_logger import list_request_errors

router = APIRouter()


@router.get(
    "/errors",
    dependencies=[Depends(require_perm("system.errors.read"))],
    summary="List recent HTTP 4xx/5xx errors",
)
async def get_error_logs(
    limit: int = Query(default=100, ge=1, le=500),
    status_code: int | None = Query(default=None, ge=400, le=599),
    search: str | None = Query(default=None),
    ip: str | None = Query(default=None),
    vk: valkey.Valkey = Depends(get_valkey_client),
) -> list[dict[str, Any]]:
    return await list_request_errors(
        vk,
        limit=limit,
        status_code=status_code,
        search=search,
        ip=ip,
    )


__all__ = ["router"]
