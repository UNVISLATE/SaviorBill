"""Consumer задач media:tasks: конвертация, ручное превью и удаление файлов.

Слушает поток Valkey ``media:tasks`` (consumer-group), конвертирует оригиналы
(webp/webm + варианты) и публикует статус в Valkey. Готовое медиа НЕ пишется в БД
напрямую: воркер публикует результат как задачу в стрим ``media:results``, а
запись в БД делает billing (владелец схемы). Биллинг и воркер друг о друге не
знают — общий контракт только через Valkey.
"""

from __future__ import annotations

import asyncio
import json
import os

import valkey.asyncio as valkey

from config import Config
from convert import ConvertError, Variant, convert, make_video_preview
from storage import Storage

_STATUS_PREFIX = "media:status:"
_FILE_PREFIX = "media:file:"


class Worker:
    """Обработчик потока медиа-задач."""

    def __init__(self, cfg: Config, vk: valkey.Valkey, storage: Storage) -> None:
        self.cfg = cfg
        self.vk = vk
        self.storage = storage
        # Ограничитель одновременно обрабатываемых задач (backpressure).
        self._sem = asyncio.Semaphore(cfg.task_concurrency)

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
        """Бесконечный цикл чтения и конкурентной обработки задач."""
        await self._ensure_group()
        while True:
            # Читаем не больше, чем есть свободных слотов (backpressure).
            count = max(1, self._sem._value)
            try:
                resp = await self.vk.xreadgroup(
                    self.cfg.group,
                    self.cfg.consumer,
                    {self.cfg.task_stream: ">"},
                    count=count,
                    block=5000,
                )
            except Exception as exc:  # noqa: BLE001
                print(f"[mediaworker] read error: {exc}", flush=True)
                await asyncio.sleep(2)
                continue
            if not resp:
                continue
            tasks = []
            for _stream, entries in resp:
                for msg_id, data in entries:
                    tasks.append(self._process_one(msg_id, data))
            if tasks:
                await asyncio.gather(*tasks)

    async def _process_one(self, msg_id: str, data: dict) -> None:
        """Обработать одну задачу под семафором; при ошибке — повтор/DLQ."""
        async with self._sem:
            try:
                await self._handle(data)
            except Exception as exc:  # noqa: BLE001
                print(f"[mediaworker] task error: {exc}", flush=True)
                await self._on_failure(data)
            finally:
                await self.vk.xack(self.cfg.task_stream, self.cfg.group, msg_id)

    async def _on_failure(self, data: dict) -> None:
        """Учесть попытку; до исчерпания — вернуть задачу в стрим, иначе — в DLQ."""
        token = data.get("token", "unknown")
        key = f"attempts:media:convert:{token}"
        n = await self.vk.incr(key)
        await self.vk.expire(key, self.cfg.status_ttl)
        if int(n) >= self.cfg.task_max_attempts:
            await self.vk.xadd(self.cfg.task_dlq_stream, {**data, "attempts": str(n)})
            await self._set_status(token, state="failed", error="max attempts exceeded")
            await self.vk.delete(key)
        else:
            # Ещё есть попытки — кладём задачу обратно в очередь.
            await self.vk.xadd(self.cfg.task_stream, data)

    async def _handle(self, data: dict) -> None:
        op = data.get("op")
        if op == "convert":
            await self._convert(data)
        elif op == "preview":
            await self._preview(data)
        elif op == "delete":
            await self._delete(data)

    async def _publish(self, variant: Variant) -> tuple[str, int]:
        """Переместить вариант в хранилище; вернуть ключ и размер."""
        tmp = os.path.join(self.cfg.uploads_dir, variant.key)
        size = os.path.getsize(tmp)
        await self.storage.put_final(variant.key, tmp, variant.mime)
        return variant.key, size

    def _variant_map(self, token: str, variants: list[Variant], sizes: dict) -> dict:
        """Собрать словарь вариантов (key/mime/size + относительный url)."""
        out: dict = {}
        for v in variants:
            base = v.key.rsplit(".", 1)[0]  # {token} или {token}.thumb -> url без ext
            out[v.name] = {
                "key": v.key,
                "mime": v.mime,
                "size": sizes.get(v.key),
                "url": f"/media/{base}",
            }
        return out

    async def _emit_result(self, fields: dict) -> None:
        """Опубликовать результат конверсии в стрим (billing запишет в БД)."""
        await self.vk.xadd(self.cfg.result_stream, fields)

    async def _convert(self, data: dict) -> None:
        token = data["token"]
        kind = data.get("kind", "image")
        owner_id = data.get("owner_id")
        src = self.storage.orig_path(token)

        await self._set_status(token, state="processing")

        try:
            variants = await convert(self.cfg, kind, src, self.cfg.uploads_dir, token)
        except ConvertError as exc:
            await self._set_status(token, state="failed", error=str(exc))
            self.storage._safe_unlink(src)
            return

        sizes: dict = {}
        for v in variants:
            key, size = await self._publish(v)
            sizes[key] = size
            # Кэш ключей вариантов для serve() — как для s3, так и для fs.
            await self.vk.hset(f"{_FILE_PREFIX}{token}", mapping={v.name: v.key})

        main = variants[0]
        vmap = self._variant_map(token, variants, sizes)
        result = {
            "op": "convert",
            "token": token,
            "kind": kind,
            "path": main.key,
            "backend": self.cfg.backend,
            "mime": main.mime,
            "status": "ready",
            "variants": json.dumps(vmap),
        }
        if main.key in sizes:
            result["size"] = str(sizes[main.key])
        if owner_id:
            result["owner_id"] = str(owner_id)
        await self._emit_result(result)
        await self._set_status(
            token, state="ready", url=f"/media/{token}", mime=main.mime
        )
        await self.vk.delete(f"attempts:media:convert:{token}")

        if not self.cfg.keep_original:
            self.storage._safe_unlink(src)

    async def _preview(self, data: dict) -> None:
        """Ручная загрузка превью для видео: пересобрать preview/preview_thumb."""
        token = data["token"]
        src = self.storage.orig_path(f"{token}.preview")
        await self._set_status(token, state="processing")
        try:
            variants = await make_video_preview(
                self.cfg, src, self.cfg.uploads_dir, token
            )
        except ConvertError as exc:
            print(f"[mediaworker] preview failed {token}: {exc}", flush=True)
            self.storage._safe_unlink(src)
            return

        sizes: dict = {}
        for v in variants:
            key, size = await self._publish(v)
            sizes[key] = size
            await self.vk.hset(f"{_FILE_PREFIX}{token}", mapping={v.name: v.key})

        vmap = self._variant_map(token, variants, sizes)
        await self._emit_result(
            {"op": "preview", "token": token, "variants": json.dumps(vmap)}
        )
        self.storage._safe_unlink(src)

    async def _delete(self, data: dict) -> None:
        payload = json.loads(data.get("payload", "{}"))
        paths = payload.get("paths", [])
        if paths:
            await self.storage.delete(paths)


__all__ = ["Worker"]
