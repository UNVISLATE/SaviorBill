"""Сборка роутера авторизации."""

from fastapi import APIRouter

from .local import router as local_router
from .password import router as password_router

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
router.include_router(local_router)
router.include_router(password_router)

__all__ = ["router"]
