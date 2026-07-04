"""Двухшаговая загрузка медиа.

Шаг 1: ``POST /media/upload?kind=<image|video|icon|avatar>``
  — проверяет JWT и права, возвращает одноразовый upload-token (TTL 1 мин).

Шаг 2: ``POST /media/upload/{upload_token}``
  — принимает файл-стрим по токену; в БД не ходит.
"""

from __future__ import annotations

import time
import uuid

import valkey.asyncio as valkey
from fastapi import APIRouter, HTTPException, Request, status

from utils import ipban
from utils.config import Config
from utils.rbac import has_perm
from utils import security
from utils.storage import Storage
from utils.telemetry import inject_carrier

router = APIRouter()

_STATUS_PREFIX = "media:status:"
_UPTOKEN_PREFIX = "media:uptoken:"
_RATE_PREFIX = "media:uprate:"
_KINDS = {"image", "video", "icon", "avatar"}
_PERM_SMALL = "media.upload"
_PERM_LARGE = "media.uploadlarge"

# Атомарный claim одноразового upload-token: HGETALL + DEL одним вызовом.
_CLAIM_TOKEN_SCRIPT = """
local data = redis.call('HGETALL', KEYS[1])
if #data == 0 then return nil end
redis.call('DEL', KEYS[1])
return data
"""


def _client_ip(request: Request) -> str:
    """IP клиента с учётом Caddy (X-Forwarded-For)."""
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
    """Проверить access-JWT и вернуть id аккаунта."""
    cfg: Config = request.app.state.cfg
    token = _bearer(request)
    try:
        return security.account_id(
            token, cfg.resolve_jwt_secret(), cfg.jwt_alg, cfg.jwt_iss
        )
    except security.InvalidToken as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc


async def _authorize(
    request: Request, acc_id: int
) -> tuple[dict | None, str | None]:
    """Прочитать права аккаунта; вернуть (perms, role_key). 401, если нет."""
    cfg: Config = request.app.state.cfg
    db = request.app.state.db
    acc = await db.account(acc_id)
    if acc is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "access denied")
    if acc.role_key == cfg.role_banned:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "account banned")
    return acc.perms, acc.role_key


async def _enforce_hourly_limit(
    request: Request, acc_id: int, perms: dict | None
) -> None:
    """Лимит загрузок в час для обычных пользователей (кроме media.uploadlarge)."""
    cfg: Config = request.app.state.cfg
    if has_perm(perms, _PERM_LARGE):
        return
    vk: valkey.Valkey = request.app.state.vk
    bucket = int(time.time()) // 3600
    key = f"{_RATE_PREFIX}{acc_id}:{bucket}"
    used = await vk.incr(key)
    if used == 1:
        await vk.expire(key, 3600)
    if used > cfg.uploads_per_hour:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "upload rate limit exceeded"
        )


@router.post("/media/upload", status_code=status.HTTP_201_CREATED)
async def request_upload_token(request: Request, kind: str = "image") -> dict:
    """Шаг 1: проверить права и выдать одноразовый upload-token."""
    cfg: Config = request.app.state.cfg
    vk: valkey.Valkey = request.app.state.vk

    ip = _client_ip(request)
    if await ipban.is_banned(vk, ip):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "temporarily banned")

    if kind not in _KINDS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "недопустимый вид медиа")

    acc_id = await _authenticate(request)
    perms, _role = await _authorize(request, acc_id)

    if has_perm(perms, _PERM_LARGE):
        max_bytes = cfg.max_bytes
    elif has_perm(perms, _PERM_SMALL):
        max_bytes = cfg.small_max_bytes
    else:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, f"недостаточно прав: {_PERM_SMALL}"
        )

    await _enforce_hourly_limit(request, acc_id, perms)

    token = uuid.uuid4().hex
    uptoken_key = f"{_UPTOKEN_PREFIX}{token}"
    await vk.hset(
        uptoken_key,
        mapping={"owner": str(acc_id), "kind": kind, "max_bytes": str(max_bytes)},
    )
    await vk.expire(uptoken_key, cfg.upload_token_ttl)
    return {
        "upload_token": token,
        "expires_in": cfg.upload_token_ttl,
        "upload_url": f"/media/upload/{token}",
    }


@router.post("/media/upload/{upload_token}", status_code=status.HTTP_202_ACCEPTED)
async def upload_file(request: Request, upload_token: str) -> dict:
    """Шаг 2: принять файл по одноразовому upload-token."""
    cfg: Config = request.app.state.cfg
    vk: valkey.Valkey = request.app.state.vk
    storage: Storage = request.app.state.storage

    ip = _client_ip(request)
    if await ipban.is_banned(vk, ip):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "temporarily banned")

    # Атомарно забрать одноразовый токен (Lua HGETALL + DEL).
    uptoken_key = f"{_UPTOKEN_PREFIX}{upload_token}"
    raw = await vk.eval(_CLAIM_TOKEN_SCRIPT, 1, uptoken_key)
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
    kind = payload.get("kind", "image")
    max_bytes = int(payload.get("max_bytes", cfg.small_max_bytes))

    # Пре-проверка: честно заявленный слишком большой Content-Length → отказ.
    clen = request.headers.get("content-length")
    if clen and clen.isdigit() and int(clen) > max_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "file too large")

    media_token = uuid.uuid4().hex
    try:
        size = await storage.save_stream(media_token, request.stream(), max_bytes)
    except ValueError:
        # Реальный объём превысил лимит — заголовок был фейковым → БАН.
        await ipban.ban(vk, ip, cfg.ban_seconds)
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "file too large")

    status_key = f"{_STATUS_PREFIX}{media_token}"
    await vk.hset(status_key, mapping={"state": "queued"})
    await vk.expire(status_key, cfg.status_ttl)
    await vk.xadd(
        cfg.task_stream,
        inject_carrier(
            {
                "op": "convert",
                "token": media_token,
                "kind": kind,
                "owner_id": str(owner_id) if owner_id else "",
                "backend": cfg.backend,
                "size": str(size),
            }
        ),
    )
    return {"token": media_token, "status": "queued"}


__all__ = ["router"]
