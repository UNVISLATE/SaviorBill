"""Пакет роутеров аналитики: /admin/analytics/basic, /admin/analytics/advanced."""

from fastapi import APIRouter

from .advanced import router as advanced_router
from .basic import router as basic_router

router = APIRouter()
router.include_router(basic_router, tags=["admin: analytics/basic"])
router.include_router(advanced_router, tags=["admin: analytics/advanced"])

__all__ = ["router"]
