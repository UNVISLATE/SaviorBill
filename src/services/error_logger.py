"""Журнал ошибок API-запросов (4xx и 5xx) для системного мониторинга."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import valkey.asyncio as valkey
from utils.datetime_utils import utc_now
from utils.degrade import VALKEY_ERRORS, note_degraded
from utils.request_context import get_current_ray_id

log = logging.getLogger("saviorbill.errors")

KEY_ERROR_LOGS_LIST = "system:error_logs"
MAX_ERRORS_STORED = 500
INSTANCE_ID = os.getenv("HOSTNAME") or os.getenv("INSTANCE_ID", "billing-1")


async def log_request_error(
    vk: valkey.Valkey,
    *,
    status_code: int,
    path: str,
    method: str,
    client_ip: str,
    error_detail: str | dict[str, Any] | list[Any],
    user_id: int | None = None,
    user_login: str | None = None,
    ray_id: str | None = None,
) -> dict[str, Any]:
    """Записать ошибку запроса в журнал."""
    effective_ray_id = ray_id or get_current_ray_id()
    now_iso = utc_now().isoformat()

    # Сериализация детали ошибки
    detail_str = (
        json.dumps(error_detail, ensure_ascii=False)
        if isinstance(error_detail, (dict, list))
        else str(error_detail)
    )

    entry = {
        "id": effective_ray_id,
        "ray_id": effective_ray_id,
        "timestamp": now_iso,
        "client_ip": client_ip,
        "user_id": user_id,
        "user_login": user_login,
        "method": method,
        "path": path,
        "status_code": status_code,
        "error_detail": detail_str,
        "instance_id": INSTANCE_ID,
    }

    try:
        raw = json.dumps(entry, ensure_ascii=False)
        await vk.lpush(KEY_ERROR_LOGS_LIST, raw)
        await vk.ltrim(KEY_ERROR_LOGS_LIST, 0, MAX_ERRORS_STORED - 1)
    except VALKEY_ERRORS as exc:
        note_degraded("errors", exc)

    return entry


async def list_request_errors(
    vk: valkey.Valkey,
    limit: int = 100,
    status_code: int | None = None,
    search: str | None = None,
    ip: str | None = None,
) -> list[dict[str, Any]]:
    """Получить список последних ошибок с фильтрацией."""
    results: list[dict[str, Any]] = []
    try:
        raw_items = await vk.lrange(KEY_ERROR_LOGS_LIST, 0, min(limit * 3, MAX_ERRORS_STORED) - 1)
        search_lower = search.lower().strip() if search else None

        for item in raw_items:
            try:
                err = json.loads(item)
                if status_code is not None and err.get("status_code") != status_code:
                    continue
                if ip and err.get("client_ip") != ip:
                    continue
                if search_lower:
                    path_match = search_lower in err.get("path", "").lower()
                    detail_match = search_lower in err.get("error_detail", "").lower()
                    ray_match = search_lower in err.get("ray_id", "").lower()
                    user_match = search_lower in (err.get("user_login") or "").lower()
                    if not (path_match or detail_match or ray_match or user_match):
                        continue
                results.append(err)
                if len(results) >= limit:
                    break
            except Exception:
                continue
    except VALKEY_ERRORS as exc:
        note_degraded("errors", exc)

    return results
