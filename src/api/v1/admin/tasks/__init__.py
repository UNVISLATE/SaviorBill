"""Админ: наблюдаемость фоновых тасков (/api/v1/admin/tasks).

Читает журнал фактов (`utils/task_log.py`) — независимая от OTEL история
последних N событий по каждому виду тасков (`media`/`lua`), хранится в
Valkey кольцевым буфером.

Подмодули монтируются с префиксами (в духе рефакторинга роутеров из п.1
задания) — единый сегмент пути задаётся здесь, а не дублируется в каждом
отдельном ``@router.get(...)`` подмодуля.
"""

from fastapi import APIRouter

from .lua import router as lua_router
from .media import router as media_router

router = APIRouter()
router.include_router(media_router, prefix="/media", tags=["admin: tasks/media"])
router.include_router(lua_router, prefix="/lua", tags=["admin: tasks/lua"])

__all__ = ["router"]
