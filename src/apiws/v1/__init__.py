from fastapi import APIRouter

from .media import router as media_router
from .tasks import router as tasks_router

router = APIRouter(prefix="/v1")
router.include_router(tasks_router)
router.include_router(media_router)

__all__ = ["router"]
