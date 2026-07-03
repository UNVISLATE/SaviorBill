from fastapi import APIRouter

from .health import router as health_router
from .upload import router as upload_router
from .serve import router as serve_router

router = APIRouter()
router.include_router(health_router)
router.include_router(upload_router)
router.include_router(serve_router)

__all__ = ["router"]
