"""Отдача медиа и ручная загрузка превью.

``GET /media/{token}``      — отдать файл: S3 → presigned redirect; fs → FileResponse.
``POST /media/{token}/preview`` — ручная загрузка постера для видео.
"""

from __future__ import annotations

import valkey.asyncio as valkey
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import FileResponse, RedirectResponse

from utils import ipban
from utils.config import Config
from utils import security
from utils.storage import Storage
from utils.telemetry import inject_carrier

router = APIRouter()

_STATUS_PREFIX = "media:status:"
_FILE_PREFIX = "media:file:"


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "0.0.0.0"


def _bearer(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "bearer token required")
    return auth.split(" ", 1)[1].strip()


async def _authenticate(request: Request) -> int:
    cfg: Config = request.app.state.cfg
    token = _bearer(request)
    try:
        return security.account_id(
            token, cfg.resolve_jwt_secret(), cfg.jwt_alg, cfg.jwt_iss
        )
    except security.InvalidToken as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc


async def _authorize(request: Request, acc_id: int) -> tuple[dict | None, str | None]:
    cfg: Config = request.app.state.cfg
    db = request.app.state.db
    acc = await db.account(acc_id)
    if acc is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "access denied")
    if acc.role_key == cfg.role_banned:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "account banned")
    return acc.perms, acc.role_key


@router.get("/media/{token}")
async def serve(request: Request, token: str):
    """Отдать медиа. S3 → presigned redirect; fs → FileResponse.

    ``token`` может нести суффикс варианта: ``{token}.thumb`` / ``{token}.preview``.
    """
    import os

    cfg: Config = request.app.state.cfg
    vk: valkey.Valkey = request.app.state.vk
    storage: Storage = request.app.state.storage

    base, _, suffix = token.partition(".")
    variant = {
        "": "main",
        "thumb": "thumb",
        "preview": "preview",
        "preview_thumb": "preview_thumb",
    }.get(suffix, "main")

    st = await vk.hgetall(f"{_STATUS_PREFIX}{base}")
    if st and st.get("state") in ("processing", "queued"):
        raise HTTPException(status.HTTP_425_TOO_EARLY, "still processing")
    if st and st.get("state") == "failed":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "conversion failed")

    if cfg.backend == "s3":
        cached = await vk.hgetall(f"{_FILE_PREFIX}{base}")
        key = cached.get(variant) if cached else None
        if not key:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
        url = await storage.presign(key)
        if not url:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
        return RedirectResponse(url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    # fs-бэкенд: воркер пишет media:file кэш; используем его, иначе — детерминированный fallback.
    cached = await vk.hgetall(f"{_FILE_PREFIX}{base}")
    if cached and cached.get(variant):
        file_key = cached.get(variant)
        file_path = os.path.join(cfg.media_dir, file_key)
        if os.path.exists(file_path):
            mime = st.get("mime") if st else None
            return FileResponse(
                file_path,
                media_type=mime or "application/octet-stream",
                headers={"Cache-Control": "public, max-age=31536000"},
            )

    # Детерминированный fallback по соглашению об именах файлов.
    if variant == "main":
        for ext, mime in ((".webp", "image/webp"), (".webm", "video/webm")):
            file_path = os.path.join(cfg.media_dir, f"{base}{ext}")
            if os.path.exists(file_path):
                return FileResponse(
                    file_path,
                    media_type=mime,
                    headers={"Cache-Control": "public, max-age=31536000"},
                )
    else:
        file_path = os.path.join(cfg.media_dir, f"{base}.{variant}.webp")
        if os.path.exists(file_path):
            return FileResponse(
                file_path,
                media_type="image/webp",
                headers={"Cache-Control": "public, max-age=31536000"},
            )

    raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")


@router.post("/media/{token}/preview", status_code=status.HTTP_202_ACCEPTED)
async def upload_preview(request: Request, token: str) -> dict:
    """Ручная загрузка превью для видео (только владелец медиа)."""
    cfg: Config = request.app.state.cfg
    vk: valkey.Valkey = request.app.state.vk
    storage: Storage = request.app.state.storage

    ip = _client_ip(request)
    if await ipban.is_banned(vk, ip):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "temporarily banned")

    acc_id = await _authenticate(request)
    await _authorize(request, acc_id)

    db = request.app.state.db
    media = await db.media_owner(token)
    if media is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "медиа не найдено")
    _mid, owner_id, mkind = media
    if owner_id != acc_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "не владелец медиа")
    if mkind != "video":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "превью только для видео")

    try:
        await storage.save_stream(
            f"{token}.preview", request.stream(), cfg.small_max_bytes
        )
    except ValueError:
        await ipban.ban(vk, ip, cfg.ban_seconds)
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "file too large")

    await vk.xadd(cfg.task_stream, inject_carrier({"op": "preview", "token": token}))
    return {"token": token, "status": "processing"}


__all__ = ["router"]
