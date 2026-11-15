"""Маршруты интерактивной документации API (Swagger UI и ReDoc)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.openapi.docs import (
    get_redoc_html,
    get_swagger_ui_html,
    get_swagger_ui_oauth2_redirect_html,
)
from fastapi.responses import HTMLResponse, RedirectResponse

from core.config import APP_NAME, AppConfig

router = APIRouter(include_in_schema=False)


@router.get("/docs", response_class=HTMLResponse)
async def swagger_ui(request: Request) -> HTMLResponse:
    settings: AppConfig = getattr(request.app.state, "settings", None)
    if settings and not settings.DOCS_ENABLED:
        raise HTTPException(status_code=404, detail="API documentation is disabled")

    return get_swagger_ui_html(
        openapi_url="/api/openapi.json",
        title=f"{APP_NAME} - Swagger UI",
        oauth2_redirect_url="/api/docs/oauth2-redirect",
        swagger_js_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js",
        swagger_css_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css",
    )


@router.get("/v1/docs")
async def v1_docs_redirect():
    """Алиас для доступа к документации по пути /api/v1/docs."""
    return RedirectResponse(url="/api/docs", status_code=307)


@router.get("/redoc", response_class=HTMLResponse)
async def redoc(request: Request) -> HTMLResponse:
    settings: AppConfig = getattr(request.app.state, "settings", None)
    if settings and not settings.DOCS_ENABLED:
        raise HTTPException(status_code=404, detail="API documentation is disabled")

    return get_redoc_html(
        openapi_url="/api/openapi.json",
        title=f"{APP_NAME} - ReDoc",
        redoc_js_url="https://cdn.jsdelivr.net/npm/redoc@next/bundles/redoc.standalone.js",
    )


@router.get("/v1/redoc")
async def v1_redoc_redirect():
    """Алиас для доступа к спецификации по пути /api/v1/redoc."""
    return RedirectResponse(url="/api/redoc", status_code=307)


@router.get("/docs/oauth2-redirect", response_class=HTMLResponse)
async def swagger_oauth2_redirect() -> HTMLResponse:
    return get_swagger_ui_oauth2_redirect_html()
