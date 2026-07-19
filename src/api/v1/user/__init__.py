"""Сборка пользовательского роутера (/api/v1/user)."""

from fastapi import APIRouter

from .me import router as me_router
from .media import router as media_router
from .oauth import router as oauth_router
from .purchases import router as purchases_router
from .services import router as services_router
from .verify import router as verify_router

router = APIRouter(prefix="/api/v1/user", tags=["user"])
router.include_router(me_router)
router.include_router(media_router)
router.include_router(services_router)
router.include_router(purchases_router)
router.include_router(oauth_router)
router.include_router(verify_router)

__all__ = ["router"]
