"""``/api/ws`` — WebSocket-роуты billing."""

from fastapi import APIRouter

from .v1 import router as v1_router

apiws_router = APIRouter(prefix="/api/ws")
apiws_router.include_router(v1_router)

__all__ = ["apiws_router"]
