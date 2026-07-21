"""Отдача медиа и ручная догрузка thumb/превью.

``GET /api/media/{token}``            — отдать файл: S3 → presigned redirect; fs → FileResponse.
``POST /api/media/{token}/preview``   — добавить ОДНО новое превью (не трогая существующие).
``POST /api/media/{token}/thumb``     — заменить единственный thumb целиком.
"""

from __future__ import annotations

import hashlib
import mimetypes
import os

import valkey.asyncio as valkey
from fastapi import APIRouter, HTTPException, Request, Security, status
from fastapi.responses import FileResponse, RedirectResponse, Response
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


def _variant_from_db(token: str, variant_name: str, variants: dict) -> tuple[str | None, str | None]:
    """Достать ``(key, mime)`` варианта из billing-JSON (``variants`` в
    ``system_media``) по имени — та же схема, что строит ``worker.py::
    _variant_dict`` (``url`` = ``/api/media/{token}{.variant_name}``), поэтому
    имя варианта надёжно восстанавливается из уже сохранённого ``url``, а не
    угадывается по именам файлов."""
    if variant_name == "main":
        media = variants.get("media") or {}
        return media.get("key"), media.get("mime")
    if variant_name == "thumb":
        thumb = variants.get("thumb") or {}
        return thumb.get("key"), thumb.get("mime")
    prefix = f"/api/media/{token}."
    for preview in variants.get("previews") or []:
        if (preview.get("url") or "") == f"{prefix}{variant_name}":
            return preview.get("key"), preview.get("mime")
    return None, None


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

    Если ``media:file:*``/``media:status:*`` в Valkey пусты (например, стек
    перезапущен, а dev-Valkey без персистентности — см. ``deploy/dev/
    docker-compose.yml``) — файл и запись в Postgres при этом целы, поэтому
    ключ/mime варианта досчитываются из billing-БД (read-only) и кэш в Valkey
    досыпается обратно, чтобы повторные запросы снова шли быстрым путём.
    """
    cfg: Config = request.app.state.cfg
    vk: valkey.Valkey = request.app.state.vk
    storage: Storage = request.app.state.storage
    db = request.app.state.db

    base, _, suffix = token.partition(".")
    variant_name = suffix or "main"

    st = await vk.hgetall(status_key(base))
    db_row: dict | None = None
    if not st:
        db_row = await db.media_variants(base)
    state = st.get("state") if st else (db_row["status"] if db_row else None)
    if variant_name == "main":
        if state in ("processing", "queued"):
            raise HTTPException(status.HTTP_425_TOO_EARLY, "still processing")
        if state == "failed":
            raise HTTPException(status.HTTP_404_NOT_FOUND, "conversion failed")

    cached = await vk.hgetall(file_key(base))
    key = cached.get(variant_name) if cached else None
    mime_from_db: str | None = None
    if not key:
        if db_row is None:
            db_row = await db.media_variants(base)
        if db_row and db_row["status"] == "ready":
            key, mime_from_db = _variant_from_db(base, variant_name, db_row["variants"])
            if key:
                await vk.hset(file_key(base), mapping={variant_name: key})
    if not key:
        # Диагностика редкого/невоспроизводимого бага: state=ready в Valkey/БД,
        # но ни кэш, ни variants-JSON не отдали ключ варианта — раньше это тихо
        # 404-илось, и найти причину постфактум (после рестарта стека, обнулившего
        # Valkey) было невозможно.
        print(
            f"[mediaworker] serve 404: token={base!r} variant={variant_name!r} "
            f"state={state!r} has_db_row={db_row is not None} "
            f"variants_keys={list((db_row or {}).get('variants') or {}) if db_row else None}",
            flush=True,
        )
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
        mime = mime_from_db
        if not mime:
            mime, _ = mimetypes.guess_type(file_path)

    # ETag от физического ``key`` (не от токена): у ``thumb`` URL стабилен и не
    # меняется при замене (см. schemas/media.py::MediaVariant — контракт "URL
    # не мигрирует при смене файла"), но сам файл за ним подменяется целиком
    # (POST /{token}/thumb). Раньше это + Cache-Control max-age=31536000 без
    # ревалидации означало, что браузер после замены thumb навечно продолжал
    # показывать старую картинку по тому же URL. main/preview физически
    # неизменны после публикации — им можно долгий immutable-кэш; thumb — явно
    # короткий max-age + must-revalidate, ETag на реальный key даёт дешёвую
    # ревалидацию (304), когда файл не менялся, и мгновенно свежий контент,
    # когда менялся.
    etag = f'"{hashlib.md5(key.encode()).hexdigest()}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers={"ETag": etag})
    if variant_name == "thumb":
        cache_control = "public, max-age=60, must-revalidate"
    else:
        cache_control = "public, max-age=31536000, immutable"
    # ``download`` в UI брал ``url`` как есть (``/api/media/{token}``, без
    # расширения) — итоговый файл на диске у пользователя оказывался без
    # расширения, приходилось дописывать вручную наугад. Расширение всегда
    # известно на сервере (из ``key`` — физического имени с расширением,
    # либо угадывается по mime) — отдаём его через ``Content-Disposition``,
    # браузер сам подставит правильное имя при скачивании независимо от
    # клиентского кода.
    ext = os.path.splitext(key)[1] or (mimetypes.guess_extension(mime) if mime else "") or ""
    download_name = f"{base}{'.' + variant_name if variant_name != 'main' else ''}{ext}"
    return FileResponse(
        file_path,
        media_type=mime or "application/octet-stream",
        headers={
            "Cache-Control": cache_control,
            "ETag": etag,
            "Content-Disposition": f'inline; filename="{download_name}"',
        },
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
