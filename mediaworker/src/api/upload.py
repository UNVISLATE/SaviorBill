"""Двухшаговая загрузка медиа.

Шаг 1: ``POST /api/media/upload``
  — проверяет JWT и права, возвращает одноразовый upload-token (TTL 1 мин).
  Вид медиа (image/video) больше не передаётся клиентом — сервер сам
  определяет его по сигнатуре файла при конвертации (см. ``utils/convert.py``);
  раньше заявленный клиентом ``kind`` не проверялся при приёме, только в
  фоновой задаче конвертации — можно было поставить в очередь видео с
  ``kind=image``. Вместо ``kind`` можно передать необязательный ``tag`` —
  короткая метка для админки/клиента (см. ``_TAG_RE``), никак не влияющая на
  обработку файла.

Шаг 2: ``POST /api/media/upload/{upload_token}``
  — принимает файл-стрим по токену; в БД не ходит.
"""

from __future__ import annotations

import re
import time
import uuid

import valkey.asyncio as valkey
from fastapi import APIRouter, HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials

from utils import ipban
from utils.authctx import authenticate, authorize, client_ip
from utils.bus_sign import sign_fields
from utils.config import Config
from utils.keys import rate_key, status_key, uptoken_key
from utils.rbac import has_perm
from utils.openapi_auth import bearer_scheme
from utils.settings import SettingsResolver
from utils.storage import Storage
from utils.task_log import TaskLog
from utils.telemetry import inject_carrier

router = APIRouter()

_PERM_SMALL = "media.upload"
_PERM_LARGE = "media.uploadlarge"
# Админское право без ограничений по размеру вообще (не совпадает с
# _PERM_LARGE, у которого есть потолок MEDIA_MAX_BYTES — см. §2.2 AUDIT.md).
_PERM_ADMIN_UNLIMITED = "admin.media.upload"
# Достаточно большой предел, чтобы Storage.save_stream не приходилось учить
# понимать "без лимита"; реального файла такого размера на диске не будет.
_UNLIMITED_BYTES = 2**62
# До 16 символов, только латиница и цифры — просто метка для UI, не влияет
# на обработку файла (в отличие от прежнего "kind").
_TAG_RE = re.compile(r"^[A-Za-z0-9]{1,16}$")

# Атомарный claim одноразового upload-token: HGETALL + DEL одним вызовом.
_CLAIM_TOKEN_SCRIPT = """
local data = redis.call('HGETALL', KEYS[1])
if #data == 0 then return nil end
redis.call('DEL', KEYS[1])
return data
"""


async def _enforce_hourly_limit(
    request: Request, acc_id: int, perms: dict | None
) -> None:
    """Лимит загрузок в час для обычных пользователей (кроме media.uploadlarge
    и admin.media.upload)."""
    if has_perm(perms, _PERM_LARGE) or has_perm(perms, _PERM_ADMIN_UNLIMITED):
        return
    settings: SettingsResolver = request.app.state.settings
    vk: valkey.Valkey = request.app.state.vk
    bucket = int(time.time()) // 3600
    key = rate_key(acc_id, bucket)
    used = await vk.incr(key)
    if used == 1:
        await vk.expire(key, 3600)
    limit = await settings.uploads_per_hour()
    if used > limit:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "upload rate limit exceeded"
        )


async def _enforce_media_count_limit(
    request: Request, acc_id: int, perms: dict | None
) -> None:
    """Лимит количества медиа-файлов на аккаунт (``user.media.limit``).

    Жёсткий отказ при превышении — без авто-удаления старых файлов
    (пользователь должен сам удалить что-то, чтобы загрузить новое).
    Не применяется к правам, снимающим ограничение размера (uploadlarge/
    admin.media.upload) — те же роли, что не упираются в размер файла, не
    должны упираться и в счётчик.
    """
    if has_perm(perms, _PERM_LARGE) or has_perm(perms, _PERM_ADMIN_UNLIMITED):
        return
    settings: SettingsResolver = request.app.state.settings
    db = request.app.state.db
    limit = await settings.user_media_limit()
    count = await db.media_count_for_owner(acc_id)
    if count >= limit:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"media count limit reached ({limit}); delete something first",
        )


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def request_upload_token(
    request: Request,
    tag: str | None = None,
    _creds: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
) -> dict:
    """Шаг 1: проверить права и выдать одноразовый upload-token.

    ``tag`` — необязательная метка (до 16 символов, латиница/цифры) только
    для удобства UI (сортировка/поиск в админке и у клиента); формат файла
    сервер определяет сам по содержимому, а не по этой метке.

    ``_creds`` не используется напрямую (реальный разбор — в
    ``authenticate()``/``bearer()`` из ``utils/authctx.py``) — параметр здесь
    только чтобы зарегистрировать HTTP Bearer security scheme в OpenAPI
    (кнопка "Authorize" и замочек в Swagger UI, см. ``utils/openapi_auth.py``).
    """
    cfg: Config = request.app.state.cfg
    vk: valkey.Valkey = request.app.state.vk
    settings: SettingsResolver = request.app.state.settings

    ip = client_ip(request)
    if await ipban.is_banned(vk, ip):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "temporarily banned")

    if tag is not None and not _TAG_RE.match(tag):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "tag: до 16 символов, только латиница и цифры",
        )

    acc_id = await authenticate(request)
    perms, _role = await authorize(request, acc_id)

    is_large = has_perm(perms, _PERM_LARGE)
    is_unlimited = has_perm(perms, _PERM_ADMIN_UNLIMITED)
    if is_unlimited:
        max_bytes = _UNLIMITED_BYTES
    elif is_large:
        max_bytes = await settings.max_bytes()
    elif has_perm(perms, _PERM_SMALL):
        max_bytes = await settings.small_max_bytes()
    else:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, f"недостаточно прав: {_PERM_SMALL}"
        )

    await _enforce_hourly_limit(request, acc_id, perms)
    await _enforce_media_count_limit(request, acc_id, perms)

    token = uuid.uuid4().hex
    uptoken_hkey = uptoken_key(token)
    await vk.hset(
        uptoken_hkey,
        mapping={
            "owner": str(acc_id),
            "tag": tag or "",
            "max_bytes": str(max_bytes),
            # Флаг права media.uploadlarge/admin.media.upload — переносим на
            # шаг 2, чтобы решить, банить ли IP за подложный Content-Length
            # (см. upload_file).
            "large": "1" if (is_large or is_unlimited) else "0",
        },
    )
    await vk.expire(uptoken_hkey, cfg.upload_token_ttl)
    return {
        "upload_token": token,
        "expires_in": cfg.upload_token_ttl,
        "upload_url": f"/api/media/upload/{token}",
    }


@router.post(
    "/upload/{upload_token}",
    status_code=status.HTTP_202_ACCEPTED,
    openapi_extra={
        # Тело читается сырым потоком (request.stream()) без File()/UploadFile,
        # чтобы не буферизовать файл целиком и соблюсти лимит размера на лету.
        # Это описание нужно только чтобы Swagger UI показал виджет выбора файла.
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
async def upload_file(request: Request, upload_token: str) -> dict:
    """Шаг 2: принять файл по одноразовому upload-token."""
    cfg: Config = request.app.state.cfg
    vk: valkey.Valkey = request.app.state.vk
    storage: Storage = request.app.state.storage
    task_log: TaskLog = request.app.state.task_log

    ip = client_ip(request)
    if await ipban.is_banned(vk, ip):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "temporarily banned")

    # Атомарно забрать одноразовый токен (Lua HGETALL + DEL).
    raw = await vk.eval(_CLAIM_TOKEN_SCRIPT, 1, uptoken_key(upload_token))
    if not raw:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "upload token not found or expired"
        )

    # Разобрать результат HGETALL (плоский список пар поле-значение).
    payload: dict = {}
    for i in range(0, len(raw), 2):
        k = raw[i].decode() if isinstance(raw[i], bytes) else raw[i]
        v = raw[i + 1].decode() if isinstance(raw[i + 1], bytes) else raw[i + 1]
        payload[k] = v

    owner_id = payload.get("owner")
    tag = payload.get("tag") or ""
    max_bytes = int(payload.get("max_bytes", cfg.small_max_bytes))
    is_large = payload.get("large") == "1"

    # Пре-проверка: честно заявленный слишком большой Content-Length → отказ.
    clen = request.headers.get("content-length")
    if clen and clen.isdigit() and int(clen) > max_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "file too large")

    media_token = uuid.uuid4().hex
    try:
        size = await storage.save_stream(media_token, request.stream(), max_bytes)
    except ValueError:
        if is_large:
            # Аккаунт с media.uploadlarge соврал про Content-Length — не бан,
            # это, скорее всего, свой человек, а не атака: просто отказ.
            raise HTTPException(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "не надо баловаться XD"
            )
        # Реальный объём превысил лимит — заголовок был фейковым → БАН.
        await ipban.ban(vk, ip, cfg.ban_seconds)
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "file too large")

    await vk.hset(status_key(media_token), mapping={"state": "queued"})
    await vk.expire(status_key(media_token), cfg.status_ttl)
    await vk.xadd(
        cfg.task_stream,
        sign_fields(
            cfg.BUS_SIGNING_KEY,
            inject_carrier(
                {
                    "op": "convert",
                    "token": media_token,
                    "tag": tag,
                    "owner_id": str(owner_id) if owner_id else "",
                    "backend": cfg.backend,
                    "size": str(size),
                }
            ),
        ),
        maxlen=cfg.task_stream_maxlen,
        approximate=True,
    )
    await task_log.record(
        kind="media", op="convert", token_or_cid=media_token, state="queued"
    )
    return {"token": media_token, "status": "queued"}


__all__ = ["router"]
