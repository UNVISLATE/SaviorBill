"""Тонкая шина медиа-задач поверх Valkey (billing-сторона).

- enqueue задач конвертации/удаления в стрим ``media:tasks`` (потребляет mediaworker);
- чтение статуса конвертации из ``media:status:{token}``.

Полноценный consumer живёт в mediaworker; billing только продюсит задачи удаления
и читает статус.
"""

from __future__ import annotations

import json

import valkey.asyncio as valkey

from observability.telemetry import inject_carrier
from security.sec.bus_sign import sign_fields

_STATUS_PREFIX = "media:status:"


class MediaBus:
    """Продюсер медиа-задач и читатель статусов (Valkey)."""

    def __init__(
        self,
        vk: valkey.Valkey,
        task_stream: str = "media:tasks",
        task_stream_maxlen: int = 10_000,
        signing_key: str = "",
    ) -> None:
        self.vk = vk
        self.task_stream = task_stream
        self.task_stream_maxlen = task_stream_maxlen
        # HMAC-ключ подписи media:tasks — общий с mediaworker.
        # Пустой = подпись отключена (dev/тесты без BUS_SIGNING_KEY).
        self.signing_key = signing_key

    async def enqueue_delete(self, backend: str, paths: list[str]) -> None:
        """Поставить задачу удаления файлов из хранилища.

        :arg backend: fs | s3.
        :arg paths: ключи/пути файлов для удаления.
        """
        if not paths:
            return
        fields = sign_fields(
            self.signing_key,
            inject_carrier(
                {
                    "op": "delete",
                    "backend": backend,
                    "payload": json.dumps({"paths": paths}),
                }
            ),
        )
        await self.vk.xadd(
            self.task_stream,
            fields,
            maxlen=self.task_stream_maxlen,
            approximate=True,
        )

    async def status(self, token: str) -> dict | None:
        """Получить статус конвертации по токену.

        :arg token: идентификатор медиа/задачи.
        :return: словарь статуса или ``None``, если запись не найдена.
        """
        data = await self.vk.hgetall(f"{_STATUS_PREFIX}{token}")
        return data or None


__all__ = ["MediaBus"]
