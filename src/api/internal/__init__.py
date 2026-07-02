"""Внутренний API (/internal) — только для доверенных сервисов в приватной сети."""

from fastapi import APIRouter

from .media import router as media_router

router = APIRouter(prefix="/internal")
router.include_router(media_router)

__all__ = ["router"]
