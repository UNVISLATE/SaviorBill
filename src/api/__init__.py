from fastapi import APIRouter

from .health import router as health_router
from .v1 import router as v1_router

api_router = APIRouter()

# health вынесен под /api, чтобы вся HTTP-поверхность billing жила под одним
# префиксом (см. app.py) и не пересекалась со статикой admin/client UI на "/"
# при совместном деплое на одном домене.
api_router.include_router(health_router, prefix="/api")
api_router.include_router(v1_router)

__all__ = ["api_router"]
