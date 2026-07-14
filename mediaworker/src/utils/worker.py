"""Consumer задач media:tasks: конвертация, доп. превью, thumb и удаление файлов.

Слушает поток Valkey ``media:tasks`` (consumer-group), конвертирует оригиналы
(webp/webm + варианты) и публикует статус в Valkey. Готовое медиа НЕ пишется в
БД напрямую: воркер публикует результат как задачу в стрим ``media:results``,
а запись в БД делает billing (владелец схемы). Биллинг и воркер друг о друге не
знают — общий контракт только через Valkey.
"""

from __future__ import annotations

import asyncio
import json
import os
import random

import valkey.asyncio as valkey

from .config import Config
from .convert import (
    ConvertError,
    Variant,
    convert,
    make_preview,
    make_thumb,
    probe_duration,
)
from .settings import SettingsResolver
from .storage import Storage
from .telemetry import inject_carrier, span_from_carrier

_STATUS_PREFIX = "media:status:"
# Статус побочных операций (доп. превью/thumb) — НАМЕРЕННО отдельный от
# _STATUS_PREFIX ключ: раньше _preview() переиспользовал статус ОСНОВНОГО
# медиа, из-за чего уже готовое видео становилось недоступным (425) на время
# пересборки превью, а при ошибке конвертации статус оставался "processing"
# навсегда (ошибка уходила только в stdout). См. implementation_plan.md §3.
_OPSTATUS_PREFIX = "media:opstatus:"
_FILE_PREFIX = "media:file:"


class Worker:
    """Обработчик потока медиа-задач."""

    def __init__(
        self, cfg: Config, vk: valkey.Valkey, storage: Storage, settings: SettingsResolver
    ) -> None:
        self.cfg = cfg
        self.vk = vk
        self.storage = storage
        self.settings = settings
        # Ограничитель одновременно обрабатываемых задач (backpressure).
        self._sem = asyncio.Semaphore(cfg.task_concurrency)

    async def _set_status(self, token: str, **fields: str) -> None:
        key = f"{_STATUS_PREFIX}{token}"
        await self.vk.hset(key, mapping={k: v for k, v in fields.items() if v})
        await self.vk.expire(key, self.cfg.status_ttl)

    async def _set_op_status(self, token: str, op: str, **fields: str) -> None:
        """Статус побочной операции (не трогает статус основного медиа)."""
        key = f"{_OPSTATUS_PREFIX}{token}:{op}"
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
            except (valkey.TimeoutError, asyncio.TimeoutError):
                # Блокирующее чтение истекло без сообщений (гонка block-таймаута
                # сервера и read-таймаута клиента) — штатная пауза, не ошибка.
                continue
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
                with span_from_carrier(f"media.task.{data.get('op', '?')}", data):
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
        elif op == "preview_add":
            await self._preview_add(data)
        elif op == "thumb_replace":
            await self._thumb_replace(data)
        elif op == "delete":
            await self._delete(data)

    async def _publish(self, variant: Variant) -> tuple[str, int]:
        """Переместить вариант в хранилище; вернуть ключ и размер."""
        tmp = os.path.join(self.cfg.uploads_dir, variant.key)
        size = os.path.getsize(tmp)
        await self.storage.put_final(variant.key, tmp, variant.mime)
        return variant.key, size

    def _variant_dict(self, token: str, v: Variant, size: int | None) -> dict:
        """Собрать словарь одного варианта (key/mime/size + относительный url)."""
        base = v.key.rsplit(".", 1)[0]  # {token}.thumb.{uuid}.webp -> без .webp
        # URL-суффикс = имя варианта ("thumb" | "preview.<uuid8>") — см.
        # convert.py docstring и serve.py (ключи ищутся по этому же имени
        # в кэше media:file:{token}).
        suffix = f".{v.name}" if v.name != "main" else ""
        return {
            "key": v.key,
            "mime": v.mime,
            "size": size,
            "url": f"/api/media/{token}{suffix}",
        }

    async def _emit_result(self, fields: dict) -> None:
        """Опубликовать результат конверсии в стрим (billing запишет в БД)."""
        await self.vk.xadd(self.cfg.result_stream, inject_carrier(fields))

    async def _convert(self, data: dict) -> None:
        token = data["token"]
        tag = data.get("tag") or None
        owner_id = data.get("owner_id")
        src = self.storage.orig_path(token)

        await self._set_status(token, state="processing")

        try:
            # Вид медиа (image/video) больше не приходит от клиента — сервер
            # определяет его сам по сигнатуре файла (см. utils/convert.py).
            kind, variants = await convert(self.cfg, src, self.cfg.uploads_dir, token)
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

        # Фото тумбим только если результат больше media.small_max_bytes —
        # маленькое фото и так уже лёгкий webp, отдельный обрезанный thumb
        # избыточен (см. implementation_plan.md §5).
        if kind == "image":
            main = variants[0]
            small_max = await self.settings.small_max_bytes()
            if sizes.get(main.key, 0) > small_max:
                thumb = await make_thumb(self.cfg, src, self.cfg.uploads_dir, token)
                key, size = await self._publish(thumb)
                sizes[key] = size
                await self.vk.hset(f"{_FILE_PREFIX}{token}", mapping={thumb.name: thumb.key})
                variants.append(thumb)

        main = variants[0]
        thumb_v = next((v for v in variants if v.name == "thumb"), None)
        preview_vs = [v for v in variants if v.name.startswith("preview.")]
        result_variants = {
            "media": self._variant_dict(token, main, sizes.get(main.key)),
            "thumb": self._variant_dict(token, thumb_v, sizes.get(thumb_v.key)) if thumb_v else None,
            "previews": [self._variant_dict(token, v, sizes.get(v.key)) for v in preview_vs],
        }
        result = {
            "op": "convert",
            "token": token,
            "kind": kind,
            "path": main.key,
            "backend": self.cfg.backend,
            "mime": main.mime,
            "status": "ready",
            "variants": json.dumps(result_variants),
        }
        if tag:
            result["tag"] = tag
        if main.key in sizes:
            result["size"] = str(sizes[main.key])
        if owner_id:
            result["owner_id"] = str(owner_id)
        await self._emit_result(result)
        await self._set_status(
            token, state="ready", url=f"/api/media/{token}", mime=main.mime, tag=tag
        )
        await self.vk.delete(f"attempts:media:convert:{token}")

        if not self.cfg.keep_original:
            self.storage._safe_unlink(src)

    async def _preview_add(self, data: dict) -> None:
        """Добавить ОДНО новое превью (не трогая уже существующие).

        ``source`` в задаче: ``"upload"`` — клиент прислал конкретный кадр
        (файл лежит во ``uploads_dir`` под ``{token}.preview_src``);
        ``"random"`` — сервер сам берёт случайный кадр из уже готового
        ``main``-файла (оригинал к этому моменту обычно уже удалён —
        см. implementation_plan.md §5.1.2, поэтому берём из main, не из
        оригинала — единственный вариант, который работает всегда).
        """
        token = data["token"]
        source = data.get("source", "random")
        try:
            if source == "upload":
                src = self.storage.orig_path(f"{token}.preview_src")
                if not os.path.exists(src):
                    raise ConvertError("исходный кадр для превью не найден")
                at = None
            else:
                src = os.path.join(self.cfg.media_dir, f"{token}.webm")
                if not os.path.exists(src):
                    raise ConvertError("main-файл недоступен для случайного кадра")
                duration = await probe_duration(src)
                at = random.uniform(0, duration) if duration else None

            preview = await make_preview(self.cfg, src, self.cfg.uploads_dir, token, at=at)
        except ConvertError as exc:
            await self._set_op_status(token, "preview", state="failed", error=str(exc))
            if source == "upload":
                self.storage._safe_unlink(self.storage.orig_path(f"{token}.preview_src"))
            return

        key, size = await self._publish(preview)
        await self.vk.hset(f"{_FILE_PREFIX}{token}", mapping={preview.name: preview.key})
        await self._emit_result(
            {
                "op": "preview_add",
                "token": token,
                "variant": json.dumps(self._variant_dict(token, preview, size)),
            }
        )
        await self._set_op_status(token, "preview", state="ready")
        if source == "upload":
            self.storage._safe_unlink(self.storage.orig_path(f"{token}.preview_src"))

    async def _thumb_replace(self, data: dict) -> None:
        """Перегенерировать (заменить) единственный thumb медиа.

        Старый физический файл удаляется из хранилища после успешной замены
        (кэш ``media:file:{token}`` перезаписывается тем же полем ``thumb``).
        """
        token = data["token"]
        src = self.storage.orig_path(f"{token}.thumb_src")
        old_key = await self.vk.hget(f"{_FILE_PREFIX}{token}", "thumb")
        try:
            if not os.path.exists(src):
                raise ConvertError("исходный файл для thumb не найден")
            thumb = await make_thumb(self.cfg, src, self.cfg.uploads_dir, token)
        except ConvertError as exc:
            await self._set_op_status(token, "thumb", state="failed", error=str(exc))
            self.storage._safe_unlink(src)
            return

        key, size = await self._publish(thumb)
        await self.vk.hset(f"{_FILE_PREFIX}{token}", mapping={thumb.name: thumb.key})
        await self._emit_result(
            {
                "op": "thumb_replace",
                "token": token,
                "variant": json.dumps(self._variant_dict(token, thumb, size)),
            }
        )
        await self._set_op_status(token, "thumb", state="ready")
        self.storage._safe_unlink(src)
        if old_key and old_key != thumb.key:
            await self.storage.delete([old_key])

    async def _delete(self, data: dict) -> None:
        payload = json.loads(data.get("payload", "{}"))
        paths = payload.get("paths", [])
        if paths:
            await self.storage.delete(paths)


__all__ = ["Worker"]
