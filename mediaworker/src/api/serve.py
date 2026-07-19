"""Отдача медиа и ручная догрузка thumb/превью.

``GET /api/media/{token}``            — отдать файл: S3 → presigned redirect; fs → FileResponse.
``POST /api/media/{token}/preview``   — добавить ОДНО новое превью (не трогая существующие).
``POST /api/media/{token}/thumb``     — заменить единственный thumb целиком.
"""

from __future__ import annotations

import mimetypes
import os

import valkey.asyncio as valkey
from fastapi import APIRouter, HTTPException, Request, Security, status
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials

from utils import ipban
from utils.authctx import authenticate, authorize, client_ip
from utils.bus_sign import sign_fields
from utils.config import Config
from utils.keys import file_key, status_key
from utils.rbac import has_perm
from utils.openapi_auth import bearer_scheme
from utils.settings import SettingsResolver
from utils.storage import Storage
from utils.task_log import TaskLog
from utils.telemetry import inject_carrier

router = APIRouter()

_PERM_LARGE = "media.uploadlarge"
# Отдельное право на доступ к preview/thumb ЧУЖОГО медиа — не совпадает с
# _PERM_LARGE (тот только про лимит размера, см. §2.2 AUDIT.md).
_PERM_MANAGE_ANY = "admin.media.manage_any"


@router.get("/{token}")
async def serve(request: Request, token: str):
    """Отдать медиа. S3 → presigned redirect; fs → FileResponse.

    ``token`` может нести суффикс варианта: ``{token}.thumb`` /
    ``{token}.preview.<uuid8>`` — суффикс ищется как есть в кэше вариантов
    ``media:file:{token}`` (см. ``worker.py::_variant_dict`` — то же имя,
    под которым воркер публикует вариант). Список превью не ограничен и не
    завязан на фиксированный набор имён — поэтому суффикс не проверяется по
    allow-листу, а ищется динамически; неизвестный/ещё не готовый суффикс —
    404 (раньше здесь молча отдавался main-файл, что вводило в заблуждение).
    """
    cfg: Config = request.app.state.cfg
    vk: valkey.Valkey = request.app.state.vk
    storage: Storage = request.app.state.storage

    base, _, suffix = token.partition(".")
    variant_name = suffix or "main"

    st = await vk.hgetall(status_key(base))
    if variant_name == "main":
        if st and st.get("state") in ("processing", "queued"):
            raise HTTPException(status.HTTP_425_TOO_EARLY, "still processing")
        if st and st.get("state") == "failed":
            raise HTTPException(status.HTTP_404_NOT_FOUND, "conversion failed")

    cached = await vk.hgetall(file_key(base))
    key = cached.get(variant_name) if cached else None
    if not key:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")

    if cfg.backend == "s3":
        url = await storage.presign(key)
        if not url:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
        return RedirectResponse(url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    try:
        file_path = storage.media_fs_path(key)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found") from None
    if not os.path.exists(file_path):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    # ``mime`` из статуса известен только для ``main`` (записан туда самим
    # воркером при завершении конвертации, см. worker.py::_set_status).
    # thumb/preview туда никогда не попадали — раньше это давало
    # ``application/octet-stream`` для них, и браузер вместо превью в теге
    # <img>/плеере скачивал файл как бинарник. thumb/preview — всегда webp
    # (см. utils/convert.py::make_thumb/make_preview), но на случай будущих
    # форматов используем угадывание по расширению, а не хардкод "image/webp".
    if variant_name == "main" and st:
        mime = st.get("mime")
    else:
        mime, _ = mimetypes.guess_type(file_path)
    return FileResponse(
        file_path,
        media_type=mime or "application/octet-stream",
        headers={"Cache-Control": "public, max-age=31536000"},
    )


async def _authorize_media_owner(
    request: Request, token: str
) -> tuple[int, bool, str]:
    """Общая проверка для догрузки thumb/preview: владелец + перм + kind.

    :return: ``(acc_id, is_large, max_bytes)``.
    """
    cfg: Config = request.app.state.cfg
    vk: valkey.Valkey = request.app.state.vk
    ip = client_ip(request)
    if await ipban.is_banned(vk, ip):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "temporarily banned")

    acc_id = await authenticate(request)
    perms, _role = await authorize(request, acc_id)
    is_large = has_perm(perms, _PERM_LARGE)
    manage_any = has_perm(perms, _PERM_MANAGE_ANY)
    settings: SettingsResolver = request.app.state.settings
    max_bytes = await (settings.max_bytes() if is_large else settings.small_max_bytes())

    db = request.app.state.db
    media = await db.media_owner(token)
    if media is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "медиа не найдено")
    _mid, owner_id, mkind = media
    if owner_id != acc_id and not manage_any:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "не владелец медиа")
    if mkind != "video":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "доступно только для видео")
    return acc_id, is_large, max_bytes


@router.post(
    "/{token}/preview",
    status_code=status.HTTP_202_ACCEPTED,
    openapi_extra={
        # Тело необязательно: пусто/Content-Length=0 -> сервер сам берёт
        # случайный кадр из готового видео; непустое тело -> конкретный кадр
        # от клиента. См. пояснение в upload.py::upload_file про сырой стрим.
        "requestBody": {
            "required": False,
            "content": {
                "application/octet-stream": {
                    "schema": {"type": "string", "format": "binary"}
                }
            },
        }
    },
)
async def add_preview(
    request: Request,
    token: str,
    _creds: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
) -> dict:
    """Добавить ОДНО новое превью в конец списка ``previews[]`` (только видео).

    Никогда не перезаписывает существующие превью — только добавляет.
    Пустое тело — сервер сам выбирает случайный кадр из уже готового видео.
    """
    cfg: Config = request.app.state.cfg
    vk: valkey.Valkey = request.app.state.vk
    storage: Storage = request.app.state.storage
    task_log: TaskLog = request.app.state.task_log

    _acc_id, is_large, max_bytes = await _authorize_media_owner(request, token)

    clen = request.headers.get("content-length")
    has_body = bool(clen) and clen.isdigit() and int(clen) > 0
    source = "upload" if has_body else "random"

    if has_body:
        ip = client_ip(request)
        try:
            await storage.save_stream(
                f"{token}.preview_src", request.stream(), max_bytes
            )
        except ValueError:
            if is_large:
                raise HTTPException(
                    status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "не надо баловаться XD"
                )
            await ipban.ban(vk, ip, cfg.ban_seconds)
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "file too large")

    await vk.xadd(
        cfg.task_stream,
        sign_fields(
            cfg.BUS_SIGNING_KEY,
            inject_carrier({"op": "preview_add", "token": token, "source": source}),
        ),
        maxlen=cfg.task_stream_maxlen,
        approximate=True,
    )
    await task_log.record(
        kind="media", op="preview_add", token_or_cid=token, state="queued"
    )
    return {"token": token, "status": "processing"}


@router.post(
    "/{token}/thumb",
    status_code=status.HTTP_202_ACCEPTED,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/octet-stream": {
                    "schema": {"type": "string", "format": "binary"}
                }
            },
        }
    },
)
async def replace_thumb(
    request: Request,
    token: str,
    _creds: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
) -> dict:
    """Загрузить новый thumb (заменяет старый целиком, только видео)."""
    cfg: Config = request.app.state.cfg
    vk: valkey.Valkey = request.app.state.vk
    storage: Storage = request.app.state.storage
    task_log: TaskLog = request.app.state.task_log

    _acc_id, is_large, max_bytes = await _authorize_media_owner(request, token)

    ip = client_ip(request)
    try:
        await storage.save_stream(f"{token}.thumb_src", request.stream(), max_bytes)
    except ValueError:
        if is_large:
            raise HTTPException(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "не надо баловаться XD"
            )
        await ipban.ban(vk, ip, cfg.ban_seconds)
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "file too large")

    await vk.xadd(
        cfg.task_stream,
        sign_fields(cfg.BUS_SIGNING_KEY, inject_carrier({"op": "thumb_replace", "token": token})),
        maxlen=cfg.task_stream_maxlen,
        approximate=True,
    )
    await task_log.record(
        kind="media", op="thumb_replace", token_or_cid=token, state="queued"
    )
    return {"token": token, "status": "processing"}


__all__ = ["router"]
