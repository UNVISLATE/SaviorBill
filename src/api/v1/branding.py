"""Публичный брендинг UI: логотип/фавикон/тема admin-панели и клиента."""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from fastapi import APIRouter, Depends, Request, Response

from dependencies.settings import SystemSettingsMngr, get_settings_mngr

router = APIRouter(prefix="/api/v1/branding", tags=["branding"])

_DEFAULT_NAMES = {"admin": "Admin", "client": "Client"}
_CACHE_CONTROL = "public, max-age=300, stale-while-revalidate=86400"


def _media_url(token: str) -> str:
    """Относительный URL отдачи медиа (обслуживает Caddy/mediaworker)."""
    return f"/api/media/{token}"


def _build_body(scope: str, raw: dict[str, str]) -> dict:
    logo = raw.get(f"ui.{scope}.logo")
    favicon = raw.get(f"ui.{scope}.favicon")
    theme_raw = raw.get(f"ui.{scope}.theme")
    return {
        "product_name": raw.get(f"ui.{scope}.product_name") or _DEFAULT_NAMES[scope],
        "logo_url": _media_url(logo) if logo else None,
        "favicon_url": _media_url(favicon) if favicon else None,
        "theme": json.loads(theme_raw) if theme_raw else {},
    }


@router.get(
    "/{scope}",
    response_model=None,
    summary="Public branding (logo/favicon/theme/product name)",
    description="Aggregates ui.{scope}.* settings into a flat JSON body. "
    "Cacheable by the browser (ETag + Cache-Control) since this rarely changes.",
)
async def get_branding(
    scope: Literal["admin", "client"],
    request: Request,
    response: Response,
    mngr: SystemSettingsMngr = Depends(get_settings_mngr),
) -> dict:
    raw = await mngr.get_group(f"ui.{scope}.")
    body = _build_body(scope, raw)
    etag = f'W/"{hashlib.md5(json.dumps(body, sort_keys=True).encode()).hexdigest()}"'

    if request.headers.get("if-none-match") == etag:
        response.status_code = 304
        response.headers["ETag"] = etag
        response.headers["Cache-Control"] = _CACHE_CONTROL
        return None

    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = _CACHE_CONTROL
    return body


__all__ = ["router"]
