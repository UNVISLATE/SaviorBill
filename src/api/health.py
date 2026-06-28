from fastapi import APIRouter, Request

from utils.config import AppConfig
from schemas.system import HealthCheck

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(request: Request):
    settings: AppConfig = request.app.state.settings
    return HealthCheck(
        status="ok",
        app_name=settings.APP_NAME,
        app_version=settings.APP_VERSION,
    )
