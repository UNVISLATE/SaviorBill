"""Сборка роутера авторизации."""

from fastapi import APIRouter, Request

from .claim import router as claim_router
from .local import router as local_router
from .password import router as password_router

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
router.include_router(local_router)
router.include_router(password_router)
router.include_router(claim_router)


@router.get("/jwks.json", summary="Public JWT key-ring")
async def jwks(request: Request) -> dict:
    """Публичные ключи верификации JWT (не содержат секретов)."""
    return {"keys": request.app.state.settings.jwt_public_keys()}


__all__ = ["router"]
