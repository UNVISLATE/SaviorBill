from fastapi import APIRouter

from .logs import router as logs_router
from .tasks import router as tasks_router

router = APIRouter(prefix="/v1")
router.include_router(tasks_router)
router.include_router(logs_router)

__all__ = ["router"]
