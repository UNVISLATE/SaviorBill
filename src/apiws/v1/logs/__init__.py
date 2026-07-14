"""``/apiws/v1/logs`` — realtime сырой вывод ffmpeg/ffprobe (для xterm.js)."""

from fastapi import APIRouter

from .media import router as media_router

router = APIRouter()
router.include_router(media_router)

__all__ = ["router"]
