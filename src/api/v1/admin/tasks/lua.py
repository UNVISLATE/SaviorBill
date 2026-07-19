"""Админ: хвост журнала lua-тасков (billing пишет ``tasklog:lua`` через LuaBus)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from dependencies.rbac import require_perm
from dependencies.task_log import get_task_log
from telemetry.task_log import TaskLog

router = APIRouter()


@router.get(
    "",
    dependencies=[Depends(require_perm("tasks.read"))],
    summary="Lua tasks log tail",
    description="Последние факты о вызовах LuaWorker: sent/ok/error "
    "(fire-and-forget задачи — только sent, ответа никогда не ждём).",
)
async def tail_lua_tasks(
    limit: int = Query(default=100, ge=1, le=500),
    task_log: TaskLog = Depends(get_task_log),
) -> list[dict]:
    return await task_log.tail("lua", limit)


__all__ = ["router"]
