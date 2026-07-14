"""Агрегатор роутеров версии v1."""

from fastapi import APIRouter

from .admin import router as admin_router
from .auth import router as auth_router
from .branding import router as branding_router
from .callback import router as callback_router
from .catalog import router as catalog_router
from .media import router as media_router
from .oauth import router as oauth_router
from .promocodes import router as promocodes_router
from .user import router as user_router

router = APIRouter()
for _r in (
    auth_router,
    oauth_router,
    catalog_router,
    branding_router,
    user_router,
    promocodes_router,
    callback_router,
    media_router,
    admin_router,
):
    router.include_router(_r)

__all__ = ["router"]
