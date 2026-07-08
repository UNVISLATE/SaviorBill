"""Пакет роутеров аналитики: /admin/analytics/basic, /admin/analytics/advanced."""

from fastapi import APIRouter

from .advanced import router as advanced_router
from .basic import router as basic_router

router = APIRouter()
router.include_router(basic_router)
router.include_router(advanced_router)

__all__ = ["router"]
