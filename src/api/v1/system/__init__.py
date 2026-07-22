"""Агрегатор роутеров ``/api/v1/system``."""

from __future__ import annotations

from fastapi import APIRouter

from .stats import router as stats_router

router = APIRouter(prefix="/api/v1/system", tags=["system: stats"])
router.include_router(stats_router)

__all__ = ["router"]
