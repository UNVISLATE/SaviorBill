"""``/api/v1/admin/logs`` — листинг job'ов realtime-логов ffmpeg/ffprobe."""

from fastapi import APIRouter

from .media import router as media_router

router = APIRouter()
router.include_router(media_router, prefix="/media", tags=["admin: logs/media"])

__all__ = ["router"]
