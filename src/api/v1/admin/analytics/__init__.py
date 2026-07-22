"""Пакет роутеров аналитики: /admin/analytics/basic, /admin/analytics/advanced.

Единый сегмент пути ("/analytics") задаётся при монтировании в
``admin/__init__.py`` — тот же паттерн, что у ``admin/tasks`` (см.
``admin/tasks/__init__.py``); подмодули объявляют только свой суффикс.
"""

from fastapi import APIRouter

from .advanced import router as advanced_router
from .basic import router as basic_router

router = APIRouter()
router.include_router(basic_router, tags=["admin: analytics/basic"])
router.include_router(advanced_router, tags=["admin: analytics/advanced"])

__all__ = ["router"]
