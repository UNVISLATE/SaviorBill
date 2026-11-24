"""Раздача скомпилированных UI-бандлов плагинов (Core Plugins Engine)."""

from __future__ import annotations

import mimetypes
import os
import re
import tempfile
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import FileResponse

from utils.config import Config

router = APIRouter()
_cfg = Config()

SLUG_PATTERN = re.compile(r"^[a-z0-9_-]{2,64}$")
_SAFE_VER_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def _safe_rel_path(base: Path, filepath: str) -> Path:
    target = (base / filepath).resolve()
    try:
        target.relative_to(base.resolve())
    except ValueError:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Access denied")
    return target


async def _fetch_s3_plugin_asset(
    cfg: Config, vk, slug: str, version: str, filepath: str
) -> Path | None:
    if not _SAFE_VER_RE.match(version) or not cfg.s3_bucket:
        return None
    cache_root = Path(tempfile.gettempdir()) / "plugin_ui_cache" / slug / version
    cache_root.mkdir(parents=True, exist_ok=True)
    cached = _safe_rel_path(cache_root, filepath)
    if cached.is_file():
        return cached

    import aioboto3
    from botocore.exceptions import ClientError

    s3_key = f"plugins/{slug}/{version}/admin/{filepath.lstrip('/')}"
    session = aioboto3.Session()
    try:
        async with session.client(
            "s3",
            endpoint_url=cfg.s3_endpoint,
            region_name=cfg.s3_region,
            aws_access_key_id=cfg.s3_key,
            aws_secret_access_key=cfg.s3_secret,
        ) as client:
            resp = await client.get_object(Bucket=cfg.s3_bucket, Key=s3_key)
            data = await resp["Body"].read()
    except ClientError:
        return None

    cached.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = cached.with_suffix(cached.suffix + ".tmp")
    tmp_path.write_bytes(data)
    os.replace(tmp_path, cached)
    return cached


@router.get("/plugins/{slug}/ui/{filepath:path}", summary="Статика микро-бандлов плагинов")
async def serve_plugin_static(slug: str, filepath: str, request: Request) -> Response:
    """Раздача скомпилированных JS/CSS-бандлов плагинов ядра для Admin UI."""
    if not SLUG_PATTERN.match(slug):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid plugin slug")

    cfg: Config = getattr(getattr(request.app, "state", None), "cfg", _cfg)
    plugins_dir = Path(cfg.DATA_DIR) / "plugins"
    admin_dir = (plugins_dir / slug / "admin").resolve()

    target_file = _safe_rel_path(admin_dir, filepath)

    if (not target_file.exists() or not target_file.is_file()) and cfg.backend == "s3":
        vk = getattr(getattr(request.app, "state", None), "vk", None)
        ver = request.query_params.get("v")
        if not ver and vk is not None:
            raw_ver = await vk.get(f"plugins:version:{slug}")
            if raw_ver:
                ver = raw_ver.decode("utf-8") if isinstance(raw_ver, bytes) else str(raw_ver)
        if ver:
            s3_cached = await _fetch_s3_plugin_asset(cfg, vk, slug, ver, filepath)
            if s3_cached is not None:
                target_file = s3_cached

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
    if suffix == ".svg":
        headers["Content-Security-Policy"] = "default-src 'none'"
        headers["Content-Disposition"] = f'attachment; filename="{target_file.name}"'
        headers["X-Content-Type-Options"] = "nosniff"

    # Cache-Busting: если передан v=... в параметрах — агрессивный immutable кэш
    if request.query_params.get("v"):
        headers["Cache-Control"] = "public, max-age=31536000, immutable"
    else:
        headers["Cache-Control"] = "no-cache, must-revalidate"

    return FileResponse(path=target_file, media_type=media_type, headers=headers)
