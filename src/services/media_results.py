"""Консьюмер результатов конвертации медиа (mediaworker → billing).

mediaworker публикует готовое медиа в стрим ``media:results`` как выполненную
задачу; billing — владелец схемы БД — потребляет её через consumer-группу и сам
записывает запись ``system_media``. Так логика записи в (изменяемую) БД живёт
только в одном сервисе.

Consumer-группа шардирует сообщения между инстансами billing (каждый результат
обрабатывается ровно один раз), поэтому распределённый лок не нужен — достаточно
уникального имени консьюмера на инстанс.
"""

from __future__ import annotations

import asyncio
import json
import logging

import valkey.asyncio as valkey
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from models.system_media import SystemMediaMngr
from utils.config import AppConfig
from utils.idempotency import once, release_once
from messaging.mediabus import MediaBus
from utils.retry import attempts, clear_attempts
from observability.telemetry import span_from_carrier

log = logging.getLogger("saviorbill.media")


class MediaResults:
    """Фоновый консьюмер стрима результатов конвертации медиа."""

    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        vk: valkey.Valkey,
        cfg: AppConfig,
    ) -> None:
        self.sm = sessionmaker
        self.vk = vk
        self.cfg = cfg
        self._task: asyncio.Task | None = None
        self._stopped = False

    async def _ensure_group(self) -> None:
        try:
            await self.vk.xgroup_create(
                self.cfg.MEDIA_RESULT_STREAM,
                self.cfg.MEDIA_RESULT_GROUP,
                id="0",
                mkstream=True,
            )
        except valkey.ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def start(self) -> None:
        """Создать группу и запустить фоновый цикл чтения."""
        await self._ensure_group()
        self._task = asyncio.create_task(self._run(), name="media-results")
        log.info("media-results the consumer is launched")

    async def stop(self) -> None:
        self._stopped = True
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run(self) -> None:
        consumer = self.cfg.instance_id
        while not self._stopped:
            try:
                resp = await self.vk.xreadgroup(
                    self.cfg.MEDIA_RESULT_GROUP,
                    consumer,
                    {self.cfg.MEDIA_RESULT_STREAM: ">"},
                    count=10,
                    block=5000,
                )
            except asyncio.CancelledError:
                raise
            except (valkey.TimeoutError, asyncio.TimeoutError):
                # Блокирующее чтение истекло без сообщений (гонка block-таймаута
                # сервера и read-таймаута клиента) — это штатная пауза, не ошибка.
                continue
            except Exception:  # noqa: BLE001 — цикл не должен падать
                log.exception("media-results: reading error")
                await asyncio.sleep(2)
                continue
            for _stream, entries in resp or []:
                for msg_id, data in entries:
                    try:
                        with span_from_carrier("media.result.consume", data):
                            await self._handle(data)
                    except Exception:  # noqa: BLE001 — одна запись не валит цикл
                        log.exception("media-results: recording error")
                        await self._on_failure(data)
                    finally:
                        await self.vk.xack(
                            self.cfg.MEDIA_RESULT_STREAM,
                            self.cfg.MEDIA_RESULT_GROUP,
                            msg_id,
                        )

    async def _on_failure(self, data: dict) -> None:
        """Учесть попытку; при исчерпании отправить результат в DLQ."""
        token = data.get("token", "unknown")
        op = data.get("op", "convert")
        key = f"media:result:{token}:{op}"
        n, exhausted = await attempts(self.vk, key, self.cfg.MEDIA_RESULT_MAX_ATTEMPTS)
        if exhausted:
            await self.vk.xadd(self.cfg.MEDIA_RESULT_DLQ, {**data, "attempts": str(n)})
            await clear_attempts(self.vk, key)
        else:
            # Снять idem-claim, чтобы повторная доставка могла обработаться заново.
            await release_once(self.vk, key)

    async def _handle(self, data: dict) -> None:
        op = data.get("op")
        token = data.get("token", "")
        # Идемпотентность: один и тот же результат конверсии обрабатываем один раз.
        if token and not await once(self.vk, f"media:result:{token}:{op}", ttl=3600):
            return
        async with self.sm() as session:
            mngr = SystemMediaMngr(session)
            if op == "preview_add":
                # Доп. превью — только добавление в конец previews[]
                variant = json.loads(data.get("variant") or "{}")
                await mngr.append_preview(token, variant)
            elif op == "thumb_replace":
                # Замена thumb целиком — старый файл нужно удалить из
                # хранилища (иначе останется висеть мусором в media_dir/s3).
                variant = json.loads(data.get("variant") or "{}")
                old_thumb = await mngr.set_thumb(token, variant)
                if old_thumb and old_thumb.get("key"):
                    media = await mngr.by_token(token)
                    if media is not None:
                        bus = MediaBus(
                            self.vk,
                            self.cfg.MEDIA_TASK_STREAM,
                            self.cfg.MEDIA_TASK_STREAM_MAXLEN,
                        )
                        await bus.enqueue_delete(media.backend, [old_thumb["key"]])
            else:  # convert
                variants = json.loads(data.get("variants") or "{}")
                owner = data.get("owner_id")
                await mngr.upsert(
                    token=data["token"],
                    kind=data.get("kind", "image"),
                    path=data["path"],
                    backend=data.get("backend", "fs"),
                    mime=data.get("mime") or None,
                    size=int(data["size"]) if data.get("size") else None,
                    owner_id=int(owner) if owner else None,
                    variants=variants,
                    status=data.get("status", "ready"),
                    tag=data.get("tag") or None,
                )
            await session.commit()
        await clear_attempts(self.vk, f"media:result:{token}:{op}")


__all__ = ["MediaResults"]
