from fastapi import APIRouter

from .health import router as health_router
from .kinds import router as kinds_router
from .status import router as status_router
from .upload import router as upload_router
from .serve import router as serve_router

router = APIRouter(prefix="/api/media")
router.include_router(health_router)
router.include_router(kinds_router)
router.include_router(status_router)
router.include_router(upload_router)
# serve_router последним: его GET /{token} — catch-all и перехватил бы /kinds
# (и любой другой односегментный путь), если бы был подключён раньше.
router.include_router(serve_router)

__all__ = ["router"]
