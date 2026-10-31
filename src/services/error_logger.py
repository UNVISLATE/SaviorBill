"""Журнал ошибок API-запросов (4xx и 5xx) для системного мониторинга."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import valkey.asyncio as valkey
from utils.datetime_utils import utc_now
from utils.degrade import VALKEY_ERRORS, note_degraded
from utils.request_context import get_current_trace_id

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
    query_params: str = "",
    duration_ms: float = 0.0,
    user_agent: str = "",
    referer: str = "",
    user_id: int | None = None,
    user_login: str | None = None,
    user_role: str | None = None,
    exception_type: str | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Записать ошибку запроса в кольцевой буфер Valkey."""
    effective_trace_id = trace_id or get_current_trace_id()
    now_iso = utc_now().isoformat()

    # Сериализация детали ошибки
    detail_str = (
        json.dumps(error_detail, ensure_ascii=False)
        if isinstance(error_detail, (dict, list))
        else str(error_detail)
    )

    entry = {
        "id": effective_trace_id,
        "trace_id": effective_trace_id,
        "timestamp": now_iso,
        "client_ip": client_ip,
        "user_id": user_id,
        "user_login": user_login,
        "user_role": user_role,
        "method": method,
        "path": path,
        "query_params": query_params,
        "status_code": status_code,
        "duration_ms": duration_ms,
        "user_agent": user_agent[:150] if user_agent else "",
        "referer": referer[:200] if referer else "",
        "exception_type": exception_type or "",
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
                # Обратная совместимость: если запись старая с ray_id
                if "trace_id" not in err and "ray_id" in err:
                    err["trace_id"] = err["ray_id"]

                if status_code is not None and err.get("status_code") != status_code:
                    continue
                if ip and err.get("client_ip") != ip:
                    continue
                if search_lower:
                    path_match = search_lower in err.get("path", "").lower()
                    query_match = search_lower in err.get("query_params", "").lower()
                    detail_match = search_lower in err.get("error_detail", "").lower()
                    trace_match = search_lower in (err.get("trace_id") or "").lower()
                    user_match = search_lower in (err.get("user_login") or "").lower()
                    agent_match = search_lower in err.get("user_agent", "").lower()
                    if not (path_match or query_match or detail_match or trace_match or user_match or agent_match):
                        continue
                results.append(err)
                if len(results) >= limit:
                    break
            except Exception:
                continue
    except VALKEY_ERRORS as exc:
        note_degraded("errors", exc)
    return results


__all__ = ["log_request_error", "list_request_errors"]
