from __future__ import annotations

from utils.config import Config
from fastapi import FastAPI

from api import router
from lifespan import lifespan

_cfg = Config()

app = FastAPI(
    title="SaviorBill mediaworker",
    version="0.0.2dev",
    lifespan=lifespan,
    docs_url="/docs" if _cfg.docs_enabled else None,
    redoc_url="/redoc" if _cfg.docs_enabled else None,
    openapi_url="/openapi.json" if _cfg.docs_enabled else None,
)

app.include_router(router)

__all__ = ["app"]
