"""Админ: хвост журнала lua-тасков (billing пишет ``tasklog:lua`` через LuaBus)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from dependencies.rbac import require_perm
from dependencies.task_log import get_task_log
from telemetry.task_log import TaskLog

router = APIRouter()


@router.get(
    "/summary",
    dependencies=[Depends(require_perm("system.tasks.summary.read"))],
    summary="Lua tasks log tail (sanitized)",
    description="То же самое, что обычный tail, но без `detail`/`trace_id` — "
    "для операторов, которым не нужна внутренняя диагностика ошибок.",
)
async def tail_lua_tasks_summary(
    limit: int = Query(default=100, ge=1, le=500),
    task_log: TaskLog = Depends(get_task_log),
) -> list[dict]:
    return await task_log.tail_summary("lua", limit)


@router.get(
    "",
    dependencies=[Depends(require_perm("system.tasks.tail.read"))],
    summary="Lua tasks log tail",
    description="Последние факты о вызовах LuaWorker: sent/ok/error "
    "(fire-and-forget задачи — только sent, ответа никогда не ждём). "
    "Содержит сырой `detail` и `trace_id` — отдельное от summary право "
    "(см. AUDIT.md §3.6).",
)
async def tail_lua_tasks(
    limit: int = Query(default=100, ge=1, le=500),
    task_log: TaskLog = Depends(get_task_log),
) -> list[dict]:
    return await task_log.tail("lua", limit)


__all__ = ["router"]
