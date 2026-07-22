from fastapi import APIRouter

from .system_stats import router as system_stats_router
from .tasks import router as tasks_router

router = APIRouter(prefix="/v1")
router.include_router(tasks_router)
router.include_router(system_stats_router, prefix="/system")

__all__ = ["router"]
