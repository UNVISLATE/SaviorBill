"""mediaworker: приём загрузки (стриминг+бан+лимит), отдача S3, статус, consumer.

Изолированный сервис домена медиа. Он сам валидирует access-JWT (общий секрет с
billing), читает роль/квоту из Postgres, пишет готовое медиа в БД и публикует
статус в Valkey. Ядро billing о воркере не знает и только читает результат.
Локальные готовые файлы отдаёт Caddy напрямую; mediaworker отдаёт S3 (presigned)
и служит fallback.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from contextlib import asynccontextmanager

import valkey.asyncio as valkey
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import RedirectResponse

import ipban
import security
from config import Config
from db import DB
from rbac import has_perm
from storage import Storage
from worker import Worker

_STATUS_PREFIX = "media:status:"
_FILE_PREFIX = "media:file:"
_RATE_PREFIX = "media:uprate:"
_UPTOKEN_PREFIX = "media:uptoken:"
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = Config.load()
    vk = valkey.from_url(cfg.valkey_url, decode_responses=True)
    storage = Storage(cfg)
    db = DB(cfg.db_dsn)
    await db.connect()
    worker = Worker(cfg, vk, storage)

    app.state.cfg = cfg
    app.state.vk = vk
    app.state.storage = storage
    app.state.db = db
    task = asyncio.create_task(worker.run())
    print(
        f"[mediaworker] {cfg.consumer} -> {cfg.valkey_url} "
        f"backend={cfg.backend} stream={cfg.task_stream}",
        flush=True,
    )
    try:
        yield
    finally:
        task.cancel()
        await db.close()
        await vk.aclose()


_DOCS_DESCRIPTION = """
Сервис приёма, конвертации и отдачи медиа (изображения/видео/иконки/аватары).
Изолирован от ядра billing: сам валидирует access-JWT (общий секрет), читает
роль/квоту из Postgres и публикует результат конвертации в стрим `media:results`.

## Аутентификация

Все эндпоинты (кроме `/health`) требуют заголовок
`Authorization: Bearer <access-JWT>` — тот же токен, что выдаёт billing на
`/api/v1/auth/login`. Секрет и алгоритм общие с billing.

## Загрузка — два шага

**Шаг 1. Получить upload-token** — `POST /media/upload?kind=<image|video|icon|avatar>`

Проверяет права и часовой лимит, выдаёт одноразовый `upload_token` (TTL
`MEDIA_UPLOAD_TOKEN_TTL`). Тело запроса не нужно. Ответ `201`:

```json
{"upload_token": "0f1e…", "expires_in": 60, "upload_url": "/media/upload/0f1e…"}
```

**Шаг 2. Отправить файл** — `POST /media/upload/{upload_token}`

Тело запроса — **сырой поток файла** (не multipart). Приём потоковый, с бегущим
счётчиком размера — полное чтение в память не выполняется. Token одноразовый
(извлекается атомарно). Ответ `202`:

```json
{"token": "9a8b…", "status": "queued"}
```

Лимиты и правила (проверяются на шаге 1, применяются на шаге 2):

- право `media.uploadlarge` → потолок `MEDIA_MAX_BYTES` (по умолчанию 50 MiB);
- право `media.upload` → потолок `MEDIA_SMALL_MAX_BYTES` (по умолчанию 1 MiB);
- частота для обычных пользователей — `MEDIA_UPLOADS_PER_HOUR` загрузок в час;
- честно заявленный `Content-Length > лимит` → `413` **без бана**;
- фейковый `Content-Length` (реальный объём превысил лимит) → `413` **+ бан IP**
  на `MEDIA_BAN_SECONDS`.

По `token` дальше проверяется статус и отдаётся файл.

## Ручная загрузка превью видео — `POST /media/{token}/preview`

Только владелец медиа и только для `kind=video`. Тело — картинка-постер (стрим,
лимит `MEDIA_SMALL_MAX_BYTES`). Ответ `202`: `{"token": …, "status": "processing"}`.

## Отдача — `GET /media/{token}[.<variant>]`

Варианты в суффиксе токена: `thumb`, `preview`, `preview_thumb` (иначе — `main`).

- `fs`-бэкенд: mediaworker отдаёт готовый файл напрямую (`FileResponse`);
- `s3`-бэкенд: `307` redirect на presigned-URL.

Коды состояния при отдаче:

- `425 Too Early` — конвертация ещё идёт (`media:status:{token}` = `queued`/`processing`);
- `404 Not Found` — конвертация провалилась либо файла/варианта нет.

## Коды ответов (сводно)

| Код | Значение |
|---|---|
| `201` | выдан upload-token (шаг 1) |
| `202` | файл/превью принят, задача поставлена |
| `307` | redirect на presigned S3-URL |
| `401` | нет/невалидный access-JWT |
| `403` | забанен (роль/IP) или недостаточно прав |
| `404` | upload-token не найден/истёк либо медиа нет |
| `413` | файл больше лимита (возможен бан IP) |
| `425` | медиа ещё конвертируется |
| `429` | превышен часовой лимит загрузок |

Полное описание домена — `docs/media.md` в репозитории.
"""

_cfg = Config.load()

app = FastAPI(
    title="SaviorBill mediaworker",
    description=_DOCS_DESCRIPTION,
    version="0.0.2dev",
    lifespan=lifespan,
    docs_url="/docs" if _cfg.docs_enabled else None,
    redoc_url="/redoc" if _cfg.docs_enabled else None,
    openapi_url="/openapi.json" if _cfg.docs_enabled else None,
)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


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


async def _authorize(request: Request, acc_id: int) -> tuple[dict | None, str | None]:
    """Прочитать права аккаунта; вернуть (perms, role_key). 401, если забанен/нет."""
    cfg: Config = request.app.state.cfg
    db: DB = request.app.state.db
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
        return  # привилегированные — без ограничения по частоте
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


@app.post("/media/upload", status_code=status.HTTP_201_CREATED)
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


@app.post("/media/upload/{upload_token}", status_code=status.HTTP_202_ACCEPTED)
async def upload_file(request: Request, upload_token: str) -> dict:
    """Шаг 2: принять файл по одноразовому upload-token."""
    cfg: Config = request.app.state.cfg
    vk: valkey.Valkey = request.app.state.vk
    storage: Storage = request.app.state.storage

    ip = _client_ip(request)
    if await ipban.is_banned(vk, ip):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "temporarily banned")

    # Атомарно забрать одноразовый token (Lua HGETALL + DEL).
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

    # Пре-проверка: честно заявленный слишком большой Content-Length -> отказ.
    clen = request.headers.get("content-length")
    if clen and clen.isdigit() and int(clen) > max_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "file too large")

    media_token = uuid.uuid4().hex
    try:
        size = await storage.save_stream(media_token, request.stream(), max_bytes)
    except ValueError:
        # Реальный объём превысил лимит — заголовок длины был фейковым -> БАН.
        await ipban.ban(vk, ip, cfg.ban_seconds)
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "file too large")

    status_key = f"{_STATUS_PREFIX}{media_token}"
    await vk.hset(status_key, mapping={"state": "queued"})
    await vk.expire(status_key, cfg.status_ttl)
    await vk.xadd(
        cfg.task_stream,
        {
            "op": "convert",
            "token": media_token,
            "kind": kind,
            "owner_id": str(owner_id) if owner_id else "",
            "backend": cfg.backend,
            "size": str(size),
        },
    )
    return {"token": media_token, "status": "queued"}


@app.post("/media/{token}/preview", status_code=status.HTTP_202_ACCEPTED)
async def upload_preview(request: Request, token: str) -> dict:
    """Ручная загрузка превью для видео (только владелец медиа)."""
    cfg: Config = request.app.state.cfg
    vk: valkey.Valkey = request.app.state.vk
    storage: Storage = request.app.state.storage
    db: DB = request.app.state.db

    ip = _client_ip(request)
    if await ipban.is_banned(vk, ip):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "temporarily banned")

    acc_id = await _authenticate(request)
    await _authorize(request, acc_id)

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

    await vk.xadd(cfg.task_stream, {"op": "preview", "token": token})
    return {"token": token, "status": "processing"}


@app.get("/media/{token}")
async def serve(request: Request, token: str):
    """Отдать медиа. S3 -> presigned redirect; fs -> файл напрямую.

    ``token`` может нести суффикс варианта: ``{token}.thumb`` / ``{token}.preview``.
    """
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

    # fs-бэкенд: отдаём файл сами.
    from fastapi.responses import FileResponse
    import os

    # Ключ варианта из кэша media:file:{base}, записанного воркером.
    cached = await vk.hgetall(f"{_FILE_PREFIX}{base}")
    if cached and cached.get(variant):
        file_key = cached.get(variant)
        file_path = os.path.join(cfg.media_dir, file_key)
        if os.path.exists(file_path):
            mime = st.get("mime") if st else None
            return FileResponse(file_path, media_type=mime or "application/octet-stream")

    # Детерминированный fallback по соглашению об именах файлов.
    if variant == "main":
        for ext in (".webp", ".webm"):
            file_path = os.path.join(cfg.media_dir, f"{base}{ext}")
            if os.path.exists(file_path):
                mime = "image/webp" if ext == ".webp" else "video/webm"
                return FileResponse(file_path, media_type=mime)
    else:
        file_path = os.path.join(cfg.media_dir, f"{base}.{variant}.webp")
        if os.path.exists(file_path):
            return FileResponse(file_path, media_type="image/webp")

    raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")


__all__ = ["app"]
