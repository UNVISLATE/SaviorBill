"""Агрегатор роутеров ``/api/v1/system``."""

from __future__ import annotations

from fastapi import APIRouter

from .cache import router as cache_router
from .errors import router as errors_router
from .security import router as security_router
from .stats import router as stats_router

router = APIRouter(prefix="/api/v1/system", tags=["system"])
router.include_router(stats_router)
router.include_router(cache_router)
router.include_router(security_router)
router.include_router(errors_router)

__all__ = ["router"]
