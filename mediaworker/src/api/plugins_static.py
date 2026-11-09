"""Раздача скомпилированных UI-бандлов плагинов (Core Plugins Engine)."""

from __future__ import annotations

import mimetypes
import re
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import FileResponse

from utils.config import Config

router = APIRouter()
_cfg = Config()

SLUG_PATTERN = re.compile(r"^[a-z0-9_-]{2,64}$")


@router.get("/plugins/{slug}/ui/{filepath:path}", summary="Статика микро-бандлов плагинов")
async def serve_plugin_static(slug: str, filepath: str, request: Request) -> Response:
    """Раздача скомпилированных JS/CSS-бандлов плагинов ядра для Admin UI."""
    if not SLUG_PATTERN.match(slug):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid plugin slug")

    plugins_dir = Path(_cfg.DATA_DIR) / "plugins"
    admin_dir = (plugins_dir / slug / "admin").resolve()

    target_file = (admin_dir / filepath).resolve()

    # Защита от Path Traversal
    try:
        target_file.relative_to(admin_dir)
    except ValueError:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Access denied")

    if not target_file.exists() or not target_file.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Static asset not found")

    # Определение MIME-типа
    suffix = target_file.suffix.lower()
    media_type = "application/octet-stream"
    if suffix in (".js", ".mjs"):
        media_type = "application/javascript; charset=utf-8"
    elif suffix == ".css":
        media_type = "text/css; charset=utf-8"
    elif suffix == ".json":
        media_type = "application/json; charset=utf-8"
    elif suffix == ".svg":
        media_type = "image/svg+xml"
    elif suffix in (".png", ".jpg", ".jpeg", ".webp"):
        media_type = mimetypes.guess_type(target_file.name)[0] or "image/png"

    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, OPTIONS",
    }

    # Cache-Busting: если передан v=... в параметрах — агрессивный immutable кэш
    if request.query_params.get("v"):
        headers["Cache-Control"] = "public, max-age=31536000, immutable"
    else:
        headers["Cache-Control"] = "no-cache, must-revalidate"

    return FileResponse(path=target_file, media_type=media_type, headers=headers)
