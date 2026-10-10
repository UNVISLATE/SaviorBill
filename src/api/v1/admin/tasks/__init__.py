"""Админ: наблюдаемость фоновых тасков (/api/v1/admin/tasks).

Читает журнал фактов (`utils/task_log.py`) и постоянный архив в PostgreSQL (`archive.py`).
"""

from fastapi import APIRouter

from .archive import router as archive_router
from .dlq import router as dlq_router
from .lua import router as lua_router
from .media import router as media_router

router = APIRouter()
router.include_router(media_router, prefix="/media", tags=["admin: tasks/media"])
router.include_router(lua_router, prefix="/lua", tags=["admin: tasks/lua"])
router.include_router(dlq_router, prefix="/dlq", tags=["admin: tasks/dlq"])
router.include_router(archive_router, prefix="/archive", tags=["admin: tasks/archive"])

__all__ = ["router"]
