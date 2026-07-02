"""Consumer задач media:tasks: конвертация и удаление файлов.

Слушает поток Valkey ``media:tasks`` (группа consumer-group), конвертирует
загруженные оригиналы (webp/webm), публикует статус, регистрирует готовое медиа в
billing (внутренний API) и обрабатывает задачи удаления.
"""

from __future__ import annotations

import asyncio
import json
import os

import httpx
import valkey.asyncio as valkey

from config import Config
from convert import ConvertError, convert, target_key
from storage import Storage

_STATUS_PREFIX = "media:status:"
_FILE_PREFIX = "media:file:"


class Worker:
    """Обработчик потока медиа-задач."""

    def __init__(self, cfg: Config, vk: valkey.Valkey, storage: Storage) -> None:
        self.cfg = cfg
        self.vk = vk
        self.storage = storage

    async def _set_status(self, token: str, **fields: str) -> None:
        key = f"{_STATUS_PREFIX}{token}"
        await self.vk.hset(key, mapping={k: v for k, v in fields.items() if v})
        await self.vk.expire(key, self.cfg.status_ttl)

    async def _ensure_group(self) -> None:
        try:
            await self.vk.xgroup_create(
                self.cfg.task_stream, self.cfg.group, id="0", mkstream=True
            )
        except valkey.ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def run(self) -> None:
        """Бесконечный цикл чтения и обработки задач."""
        await self._ensure_group()
        while True:
            try:
                resp = await self.vk.xreadgroup(
                    self.cfg.group,
                    self.cfg.consumer,
                    {self.cfg.task_stream: ">"},
                    count=1,
                    block=0,
                )
            except Exception as exc:  # noqa: BLE001
                print(f"[mediaworker] read error: {exc}", flush=True)
                await asyncio.sleep(2)
                continue
            if not resp:
                continue
            for _stream, entries in resp:
                for msg_id, data in entries:
                    try:
                        await self._handle(data)
                    except Exception as exc:  # noqa: BLE001
                        print(f"[mediaworker] task error: {exc}", flush=True)
                    finally:
                        await self.vk.xack(self.cfg.task_stream, self.cfg.group, msg_id)

    async def _handle(self, data: dict) -> None:
        op = data.get("op")
        if op == "convert":
            await self._convert(data)
        elif op == "delete":
            await self._delete(data)

    async def _convert(self, data: dict) -> None:
        token = data["token"]
        kind = data.get("kind", "image")
        owner_id = data.get("owner_id")
        src = self.storage.orig_path(token)
        key, mime = target_key(token, kind)
        tmp = os.path.join(self.cfg.uploads_dir, key)

        try:
            await convert(self.cfg, kind, src, tmp)
        except ConvertError as exc:
            await self._set_status(token, state="failed", error=str(exc))
            self.storage._safe_unlink(src)
            self.storage._safe_unlink(tmp)
            return

        size = os.path.getsize(tmp)
        await self.storage.put_final(key, tmp, mime)

        if self.cfg.backend == "s3":
            await self.vk.hset(
                f"{_FILE_PREFIX}{token}", mapping={"key": key, "mime": mime}
            )

        await self._set_status(token, state="ready", url=f"/media/{token}", mime=mime)
        await self._register(token, kind, key, mime, size, owner_id)

        if not self.cfg.keep_original:
            self.storage._safe_unlink(src)

    async def _register(
        self,
        token: str,
        kind: str,
        key: str,
        mime: str,
        size: int,
        owner_id: str | None,
    ) -> None:
        body = {
            "token": token,
            "kind": kind,
            "path": key,
            "backend": self.cfg.backend,
            "mime": mime,
            "size": size,
        }
        if owner_id:
            body["owner_id"] = int(owner_id)
        async with httpx.AsyncClient(timeout=15) as client:
            try:
                r = await client.post(
                    f"{self.cfg.billing_url}/internal/media/register",
                    json=body,
                    headers={"Authorization": f"Bearer {self.cfg.service_token}"},
                )
                if r.status_code >= 400:
                    print(
                        f"[mediaworker] register failed {r.status_code}: {r.text}",
                        flush=True,
                    )
            except Exception as exc:  # noqa: BLE001
                print(f"[mediaworker] register error: {exc}", flush=True)

    async def _delete(self, data: dict) -> None:
        payload = json.loads(data.get("payload", "{}"))
        paths = payload.get("paths", [])
        if paths:
            await self.storage.delete(paths)


__all__ = ["Worker"]
