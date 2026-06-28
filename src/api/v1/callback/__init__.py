"""Сборка роутеров колбэков (/api/v1/callback)."""

from fastapi import APIRouter

from .oauth import router as oauth_cb_router
from .payment import router as payment_cb_router

router = APIRouter()
router.include_router(payment_cb_router)
router.include_router(oauth_cb_router)

__all__ = ["router"]
