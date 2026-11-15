"""Админ: настройки системы (/api/v1/admin/settings)."""

from __future__ import annotations

from fastapi import APIRouter

from .fx import router as fx_router
from .ratelimits import router as ratelimits_router
from .raw import router as raw_router
from .secrets import router as secrets_router
from .security import router as security_router
from .smtp import router as smtp_router

router = APIRouter()
router.include_router(security_router, prefix="/security")
router.include_router(ratelimits_router, prefix="/ratelimits")
router.include_router(raw_router, prefix="/raw")
router.include_router(secrets_router, prefix="/secrets")
router.include_router(fx_router, prefix="/fx")
router.include_router(smtp_router, prefix="/smtp")

__all__ = ["router"]
