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
from .bus_sign import sign_fields, verify_fields
from .keys import file_key, job_lock_key, opstatus_key, status_key
from .proclog import ProcLog
from .settings import SettingsResolver
from .storage import Storage
from .task_log import TaskLog
from .telemetry import inject_carrier, span_from_carrier

# Статус побочных операций (доп. превью/thumb) — НАМЕРЕННО отдельный от
# основного статуса медиа (см. ``keys.opstatus_key``): раньше _preview()
# переиспользовал статус ОСНОВНОГО медиа, из-за чего уже готовое видео
# становилось недоступным (425) на время пересборки превью, а при ошибке
# конвертации статус оставался "processing" навсегда (ошибка уходила только
# в stdout).


class Worker:
    """Обработчик потока медиа-задач."""

    def __init__(
        self,
        cfg: Config,
        vk: valkey.Valkey,
        storage: Storage,
        settings: SettingsResolver,
        task_log: TaskLog,
        proc_log: ProcLog,
    ) -> None:
        self.cfg = cfg
        self.vk = vk
        self.storage = storage
        self.settings = settings
        self.task_log = task_log
        self.proc_log = proc_log
        # Ограничитель одновременно обрабатываемых задач (backpressure).
        self._sem = asyncio.Semaphore(cfg.task_concurrency)

    async def _set_status(self, token: str, **fields: str) -> None:
        key = status_key(token)
        await self.vk.hset(key, mapping={k: v for k, v in fields.items() if v})
        await self.vk.expire(key, self.cfg.status_ttl)

    async def _set_op_status(self, token: str, op: str, **fields: str) -> None:
        """Статус побочной операции (не трогает статус основного медиа)."""
        key = opstatus_key(token, op)
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
        """Обработать одну задачу под семафором; при ошибке — повтор/DLQ.

        Лок ``job_lock_key(op, token)`` — защита от гонки с reclaim: долгая
        конвертация видео может не успеть ack за ``MEDIA_RECLAIM_MIN_IDLE_MS``,
        хотя обработка ещё жива; без лока reclaim запустил бы дубликат той же
        задачи конкурентно с оригиналом (см. ``reclaim_once``), и то, какой из
        двух результатов "победит" в статусе — гонка. Держатель лока — либо
        этот же процесс (self-reclaim не создаёт дубликата), либо другая
        реплика воркера (если их несколько).
        """
        async with self._sem:
            lock_key = None
            try:
                if not verify_fields(self.cfg.BUS_SIGNING_KEY, data):
                    # Задача с неверной/отсутствующей подписью — не исполняем:
                    # подделка или рассинхронизация BUS_SIGNING_KEY между
                    # сервисами. Ack без повтора (не через _on_failure/reclaim —
                    # иначе честно повторяли бы заведомо поддельное сообщение).
                    print(
                        f"[mediaworker] task {msg_id} rejected: invalid signature",
                        flush=True,
                    )
                    return
                op = data.get("op", "?")
                token = data.get("token", "unknown")
                lock_key = job_lock_key(op, token)
                got_lock = bool(
                    await self.vk.set(
                        lock_key, self.cfg.consumer, nx=True, ex=self.cfg.job_lock_ttl_sec
                    )
                )
                if not got_lock:
                    # Уже в обработке (этим же воркером после self-reclaim,
                    # либо другой репликой) — не трогаем, держатель лока сам
                    # доведёт задачу до конца и опубликует результат/статус.
                    print(
                        f"[mediaworker] task {msg_id} skipped: {op}:{token} already in flight",
                        flush=True,
                    )
                    lock_key = None  # не наш — не освобождать в finally
                    return
                with span_from_carrier(f"media.task.{op}", data):
                    await self._handle(data)
            except Exception as exc:  # noqa: BLE001
                print(f"[mediaworker] task error: {exc}", flush=True)
                await self._on_failure(data)
            finally:
                if lock_key is not None:
                    await self.vk.delete(lock_key)
                await self.vk.xack(self.cfg.task_stream, self.cfg.group, msg_id)

    async def _on_failure(self, data: dict) -> None:
        """Учесть попытку; до исчерпания — вернуть задачу в стрим, иначе — в DLQ."""
        token = data.get("token", "unknown")
        key = f"attempts:media:convert:{token}"
        n = await self.vk.incr(key)
        await self.vk.expire(key, self.cfg.status_ttl)
        if int(n) >= self.cfg.task_max_attempts:
            await self._to_dlq(data, attempts=int(n), reason="max attempts exceeded")
            await self.vk.delete(key)
        else:
            # Ещё есть попытки — кладём задачу обратно в очередь. Подпись/ts
            # пересобираются заново (не переносим старые ts/sig): к моменту
            # повторной обработки исходный ts может выйти за anti-replay-окно
            # и задача была бы отклонена как "просроченная".
            fresh = {k: v for k, v in data.items() if k not in ("ts", "sig")}
            await self.vk.xadd(
                self.cfg.task_stream,
                sign_fields(self.cfg.BUS_SIGNING_KEY, fresh),
                maxlen=self.cfg.task_stream_maxlen,
                approximate=True,
            )

    async def _to_dlq(self, data: dict, *, attempts: int, reason: str) -> None:
        """Переместить задачу в DLQ и пометить связанный токен как failed.

        Общий хвост для двух путей исчерпания попыток: обычного (счётчик в
        ``_on_failure``) и через reclaim мёртвых консьюмеров (``times_delivered``
        из XPENDING, см. ``reclaim_once``).
        """
        token = data.get("token", "unknown")
        op = data.get("op", "?")
        await self.vk.xadd(
            self.cfg.task_dlq_stream,
            {**data, "attempts": str(attempts)},
            maxlen=self.cfg.task_stream_maxlen,
            approximate=True,
        )
        await self._set_status(token, state="failed", error=reason)
        await self.task_log.record(
            kind="media",
            op=op,
            token_or_cid=token,
            state="failed",
            detail=reason,
        )

    async def reclaim_once(self) -> None:
        """Подхватить PEL-записи ``media:tasks``, зависшие у мёртвых консьюмеров.

        Раньше при крахе процесса посреди обработки сообщение навсегда
        оставалось "pending" в consumer-group — никто его не переисполнял.
        ``XPENDING ... IDLE`` отдаёт ``times_delivered`` ДО захвата, поэтому
        решение "reclaim vs DLQ" принимается заранее (в отличие от
        XAUTOCLAIM, который такой информации не даёт).
        """
        try:
            pending = await self.vk.xpending_range(
                self.cfg.task_stream,
                self.cfg.group,
                min="-",
                max="+",
                count=50,
                idle=self.cfg.reclaim_min_idle_ms,
            )
        except valkey.ResponseError:
            return  # стрим/группа ещё не созданы — ничего реклеймить
        for item in pending or []:
            msg_id = item["message_id"]
            delivery_count = int(item.get("times_delivered", 1))
            if delivery_count > self.cfg.task_max_attempts:
                rows = await self.vk.xrange(self.cfg.task_stream, msg_id, msg_id)
                data = dict(rows[0][1]) if rows else {}
                await self.vk.xack(self.cfg.task_stream, self.cfg.group, msg_id)
                if data:
                    await self._to_dlq(
                        data, attempts=delivery_count, reason="max attempts exceeded (reclaim)"
                    )
                continue
            claimed = await self.vk.xclaim(
                self.cfg.task_stream,
                self.cfg.group,
                self.cfg.consumer,
                min_idle_time=self.cfg.reclaim_min_idle_ms,
                message_ids=[msg_id],
            )
            for claimed_id, fields in claimed:
                await self._process_one(claimed_id, fields)

    async def reclaim_loop(self) -> None:
        """Периодический sweep зависших задач (см. ``reclaim_once``)."""
        while True:
            await asyncio.sleep(self.cfg.reclaim_interval_sec)
            await self.reclaim_once()


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
        await self.vk.xadd(
            self.cfg.result_stream,
            sign_fields(self.cfg.BUS_SIGNING_KEY, inject_carrier(fields)),
            maxlen=self.cfg.result_stream_maxlen,
            approximate=True,
        )

    def _cleanup_partial(self, token: str, src: str) -> None:
        """Удалить оригинал и все недоопубликованные варианты после сбоя конверсии.

        ``convert_video`` — многошаговый (main → thumb → preview): если упал не
        первый шаг, предыдущие ffmpeg-выходы уже лежат в ``uploads_dir``, но
        ``variants`` из-за исключения так и не вернулись вызывающей стороне, а
        значит никогда не попадут в ``_publish``/удаление — без явной чистки по
        маске ``{token}.*`` они бы оставались мусором в uploads_dir навсегда.
        """
        import glob

        for path in glob.glob(os.path.join(self.cfg.uploads_dir, f"{token}.*")):
            self.storage._safe_unlink(path)
        self.storage._safe_unlink(src)

    async def _convert(self, data: dict) -> None:
        token = data["token"]
        tag = data.get("tag") or None
        owner_id = data.get("owner_id")
        src = self.storage.orig_path(token)

        await self._set_status(token, state="processing")
        await self.task_log.record(
            kind="media", op="convert", token_or_cid=token, state="processing"
        )
        job_id = await self.proc_log.start_job(op="convert", token=token)

        async def sink(chunk: str) -> None:
            await self.proc_log.append(job_id, chunk)

        try:
            # Вид медиа (image/video) больше не приходит от клиента — сервер
            # определяет его сам по сигнатуре файла (см. utils/convert.py).
            kind, variants = await convert(
                self.cfg, src, self.cfg.uploads_dir, token, on_output=sink
            )
        except ConvertError as exc:
            await self._set_status(token, state="failed", error=str(exc))
            await self.task_log.record(
                kind="media",
                op="convert",
                token_or_cid=token,
                state="failed",
                detail=str(exc),
            )
            await self.proc_log.finish_job(job_id, "failed")
            # Видео конвертируется в несколько шагов (main -> thumb -> preview);
            # если упал не первый шаг, предыдущие уже созданы в uploads_dir, но
            # никогда не были опубликованы (put_final) и не попали в variants —
            # без явной чистки они бы остались висеть мусором навсегда.
            self._cleanup_partial(token, src)
            return

        sizes: dict = {}
        for v in variants:
            key, size = await self._publish(v)
            sizes[key] = size
            # Кэш ключей вариантов для serve() — как для s3, так и для fs.
            await self.vk.hset(file_key(token), mapping={v.name: v.key})

        # Фото тумбим только если результат больше media.small_max_bytes —
        # маленькое фото и так уже лёгкий webp, отдельный обрезанный thumb избыточен
        if kind == "image":
            main = variants[0]
            small_max = await self.settings.small_max_bytes()
            if sizes.get(main.key, 0) > small_max:
                thumb = await make_thumb(self.cfg, src, self.cfg.uploads_dir, token)
                key, size = await self._publish(thumb)
                sizes[key] = size
                await self.vk.hset(file_key(token), mapping={thumb.name: thumb.key})
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
        await self.task_log.record(
            kind="media", op="convert", token_or_cid=token, state="ready"
        )
        await self.proc_log.finish_job(job_id, "ready")
        await self.vk.delete(f"attempts:media:convert:{token}")

        if not self.cfg.keep_original:
            self.storage._safe_unlink(src)

    async def _preview_add(self, data: dict) -> None:
        """Добавить ОДНО новое превью (не трогая уже существующие)."""
        token = data["token"]
        source = data.get("source", "random")
        await self.task_log.record(
            kind="media", op="preview_add", token_or_cid=token, state="processing"
        )
        job_id = await self.proc_log.start_job(op="preview_add", token=token)

        async def sink(chunk: str) -> None:
            await self.proc_log.append(job_id, chunk)

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

            preview = await make_preview(
                self.cfg, src, self.cfg.uploads_dir, token, at=at, on_output=sink
            )
        except ConvertError as exc:
            await self._set_op_status(token, "preview", state="failed", error=str(exc))
            await self.task_log.record(
                kind="media",
                op="preview_add",
                token_or_cid=token,
                state="failed",
                detail=str(exc),
            )
            await self.proc_log.finish_job(job_id, "failed")
            if source == "upload":
                self.storage._safe_unlink(self.storage.orig_path(f"{token}.preview_src"))
            return

        key, size = await self._publish(preview)
        await self.vk.hset(file_key(token), mapping={preview.name: preview.key})
        await self._emit_result(
            {
                "op": "preview_add",
                "token": token,
                "variant": json.dumps(self._variant_dict(token, preview, size)),
            }
        )
        await self._set_op_status(token, "preview", state="ready")
        await self.task_log.record(
            kind="media", op="preview_add", token_or_cid=token, state="ready"
        )
        await self.proc_log.finish_job(job_id, "ready")
        if source == "upload":
            self.storage._safe_unlink(self.storage.orig_path(f"{token}.preview_src"))

    async def _thumb_replace(self, data: dict) -> None:
        """Перегенерировать (заменить) единственный thumb медиа.

        Старый физический файл удаляется из хранилища после успешной замены
        (кэш ``media:file:{token}`` перезаписывается тем же полем ``thumb``).
        """
        token = data["token"]
        await self.task_log.record(
            kind="media", op="thumb_replace", token_or_cid=token, state="processing"
        )
        job_id = await self.proc_log.start_job(op="thumb_replace", token=token)

        async def sink(chunk: str) -> None:
            await self.proc_log.append(job_id, chunk)

        src = self.storage.orig_path(f"{token}.thumb_src")
        old_key = await self.vk.hget(file_key(token), "thumb")
        try:
            if not os.path.exists(src):
                raise ConvertError("исходный файл для thumb не найден")
            thumb = await make_thumb(self.cfg, src, self.cfg.uploads_dir, token, on_output=sink)
        except ConvertError as exc:
            await self._set_op_status(token, "thumb", state="failed", error=str(exc))
            await self.task_log.record(
                kind="media",
                op="thumb_replace",
                token_or_cid=token,
                state="failed",
                detail=str(exc),
            )
            await self.proc_log.finish_job(job_id, "failed")
            self.storage._safe_unlink(src)
            return

        key, size = await self._publish(thumb)
        await self.vk.hset(file_key(token), mapping={thumb.name: thumb.key})
        await self._emit_result(
            {
                "op": "thumb_replace",
                "token": token,
                "variant": json.dumps(self._variant_dict(token, thumb, size)),
            }
        )
        await self._set_op_status(token, "thumb", state="ready")
        await self.task_log.record(
            kind="media", op="thumb_replace", token_or_cid=token, state="ready"
        )
        await self.proc_log.finish_job(job_id, "ready")
        self.storage._safe_unlink(src)
        if old_key and old_key != thumb.key:
            await self.storage.delete([old_key])

    async def _delete(self, data: dict) -> None:
        payload = json.loads(data.get("payload", "{}"))
        paths = payload.get("paths", [])
        if paths:
            await self.storage.delete(paths)


__all__ = ["Worker"]
