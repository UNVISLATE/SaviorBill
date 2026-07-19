from fastapi import APIRouter, Request

from core.config import AppConfig, APP_NAME, APP_VERSION
from schemas.system import HealthCheck

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(request: Request):
    settings: AppConfig = request.app.state.settings
    return HealthCheck(
        status="ok",
        app_name=APP_NAME,
        app_version=APP_VERSION,
    )
