"""mediaworker: приём загрузки (стриминг+бан), отдача S3, статус, consumer.

Изолированный сервис. Ядро billing файлы не трогает: авторизацию загрузки и
регистрацию готового медиа делает через внутренний API billing, конвертацию —
ffmpeg, очередь и статусы — Valkey. Локальные готовые файлы отдаёт Caddy напрямую;
mediaworker отдаёт только S3 (presigned) и служит fallback.
"""

from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager

import httpx
import valkey.asyncio as valkey
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import RedirectResponse

import ipban
from config import Config
from storage import Storage
from worker import Worker

_STATUS_PREFIX = "media:status:"
_FILE_PREFIX = "media:file:"


def _client_ip(request: Request) -> str:
    """IP клиента с учётом Caddy (X-Forwarded-For)."""
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "0.0.0.0"


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = Config.load()
    vk = valkey.from_url(cfg.valkey_url, decode_responses=True)
    storage = Storage(cfg)
    worker = Worker(cfg, vk, storage)

    app.state.cfg = cfg
    app.state.vk = vk
    app.state.storage = storage
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
        await vk.aclose()


app = FastAPI(title="SaviorBill mediaworker", lifespan=lifespan)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


async def _authorize(cfg: Config, user_token: str, kind: str) -> dict:
    """Спросить billing, можно ли грузить и какой лимит объёма."""
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(
            f"{cfg.billing_url}/internal/media/authorize",
            json={"user_token": user_token, "kind": kind},
            headers={"Authorization": f"Bearer {cfg.service_token}"},
        )
    if r.status_code == 200:
        return r.json()
    detail = "authorization failed"
    try:
        detail = r.json().get("detail", detail)
    except Exception:  # noqa: BLE001
        pass
    raise HTTPException(r.status_code, detail)


@app.post("/media/upload", status_code=status.HTTP_201_CREATED)
async def upload(request: Request, kind: str = "image") -> dict:
    """Потоково принять файл: авторизация, контроль объёма, постановка конверсии."""
    cfg: Config = request.app.state.cfg
    vk: valkey.Valkey = request.app.state.vk
    storage: Storage = request.app.state.storage

    ip = _client_ip(request)
    if await ipban.is_banned(vk, ip):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "temporarily banned")

    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "bearer token required")
    user_token = auth.split(" ", 1)[1].strip()

    info = await _authorize(cfg, user_token, kind)
    owner_id = info["owner_id"]
    max_bytes = int(info["max_bytes"])

    # Пре-проверка: честно заявленный слишком большой размер -> отказ БЕЗ бана.
    clen = request.headers.get("content-length")
    if clen and clen.isdigit() and int(clen) > max_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "file too large")

    token = uuid.uuid4().hex
    try:
        size = await storage.save_stream(token, request.stream(), max_bytes)
    except ValueError:
        # Реальный объём превысил лимит — заголовок длины был фейковым -> БАН.
        await ipban.ban(vk, ip, cfg.ban_seconds)
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "file too large")

    status_key = f"{_STATUS_PREFIX}{token}"
    await vk.hset(status_key, mapping={"state": "processing"})
    await vk.expire(status_key, cfg.status_ttl)
    await vk.xadd(
        cfg.task_stream,
        {
            "op": "convert",
            "token": token,
            "kind": kind,
            "owner_id": str(owner_id),
            "backend": cfg.backend,
            "size": str(size),
        },
    )
    return {"token": token, "status": "processing"}


@app.get("/media/{token}")
async def serve(request: Request, token: str):
    """Отдать медиа: S3 -> presigned redirect; локально обслуживает Caddy."""
    cfg: Config = request.app.state.cfg
    vk: valkey.Valkey = request.app.state.vk
    storage: Storage = request.app.state.storage

    st = await vk.hgetall(f"{_STATUS_PREFIX}{token}")
    if st and st.get("state") == "processing":
        raise HTTPException(status.HTTP_425_TOO_EARLY, "still processing")
    if st and st.get("state") == "failed":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "conversion failed")

    if cfg.backend == "s3":
        cached = await vk.hgetall(f"{_FILE_PREFIX}{token}")
        if not cached:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
        url = await storage.presign(cached["key"])
        if not url:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
        return RedirectResponse(url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    # Локальный бэкенд: обычно файл отдаёт Caddy; сюда попадаем при промахе.
    raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")


__all__ = ["app"]
