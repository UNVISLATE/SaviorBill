"""Внутренние API-эндпоинты для взаимодействия с воркерами (LuaWorker, MediaWorker)."""

from __future__ import annotations

from fastapi import APIRouter

from .email import router as internal_email_router
from .service_keys import router as internal_servicekeys_router

router = APIRouter(prefix="/api/v1/internal", tags=["internal"])
router.include_router(internal_servicekeys_router)
router.include_router(internal_email_router)

__all__ = ["router"]
