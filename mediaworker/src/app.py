from __future__ import annotations

from utils.config import Config
from fastapi import FastAPI

from api import router
from lifespan import lifespan
from utils.telemetry import install_access_log_filter, setup_observability

_cfg = Config()

APP_NAME = "saviormedia"
APP_VERSION = "0.0.2dev"

install_access_log_filter()

app = FastAPI(
    title=f"SaviorBill - {APP_NAME}",
    version=APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs" if _cfg.docs_enabled else None,
    redoc_url="/redoc" if _cfg.docs_enabled else None,
    openapi_url="/openapi.json" if _cfg.docs_enabled else None,
)

# Метрики Prometheus + трейсинг OpenTelemetry (по флагам METRICS_ENABLED/OTEL_ENABLED).
setup_observability(app, _cfg, APP_NAME, APP_VERSION)

app.include_router(router)

__all__ = ["app"]


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=_cfg.MEDIA_HOST, port=_cfg.MEDIA_PORT)
