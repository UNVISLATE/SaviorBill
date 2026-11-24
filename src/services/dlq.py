"""Мёртвые очереди (DLQ): просмотр, повтор и метрика длины."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import valkey.asyncio as valkey

from core.config import AppConfig
from security.sec.bus_sign import sign_fields
from telemetry.metrics import dlq_pending
from utils.datetime_utils import utc_now
from utils.retry import clear_attempts

log = logging.getLogger("saviorbill.dlq")


@dataclass(frozen=True, slots=True)
class DLQSpec:
    """Описание одной мёртвой очереди и способа вернуть задачу в работу."""

    #: Ключ Valkey с мёртвыми записями.
    dead_key: str
    #: Куда возвращать при повторе.
    target_key: str
    #: ``stream`` — XADD с пересборкой подписи, ``zset`` — ZADD члена очереди.
    kind: str


#: Публичные имена очередей (используются в путях админского API).
DLQ_QUEUES = ("billing", "media_tasks", "media_results")


def _specs(cfg: AppConfig) -> dict[str, DLQSpec]:
    return {
        "billing": DLQSpec(
            cfg.BILLING_QUEUE_DLQ,
            getattr(cfg, "BILLING_READY_STREAM", "billing:tasks:ready"),
            "outbox",
        ),
        "media_tasks": DLQSpec(cfg.MEDIA_TASK_DLQ, cfg.MEDIA_TASK_STREAM, "stream"),
        "media_results": DLQSpec(
            cfg.MEDIA_RESULT_DLQ, cfg.MEDIA_RESULT_STREAM, "stream"
        ),
    }


class DeadLetters:
    """Чтение и повтор задач из мёртвых очередей."""

    def __init__(
        self,
        vk: valkey.Valkey,
        cfg: AppConfig,
        session=None,
    ) -> None:
        self.vk = vk
        self.cfg = cfg
        self.s = session
        self.specs = _specs(cfg)

    async def overview(self, limit: int = 50) -> dict:
        """Длина и последние записи каждой мёртвой очереди."""
        out: dict = {}
        for name, spec in self.specs.items():
            entries = await self.vk.xrevrange(spec.dead_key, count=limit)
            out[name] = {
                "total": int(await self.vk.xlen(spec.dead_key) or 0),
                "items": [
                    {"id": _s(eid), "fields": {_s(k): _s(v) for k, v in data.items()}}
                    for eid, data in entries
                ],
            }
        return out

    async def refresh_metrics(self) -> None:
        """Обновить gauge длины мёртвых очередей."""
        for name, spec in self.specs.items():
            dlq_pending.labels(queue=name).set(
                int(await self.vk.xlen(spec.dead_key) or 0)
            )

    async def _entry(self, spec: DLQSpec, entry_id: str) -> dict | None:
        rows = await self.vk.xrange(spec.dead_key, min=entry_id, max=entry_id, count=1)
        if not rows:
            return None
        return {_s(k): _s(v) for k, v in rows[0][1].items()}

    async def drop(self, queue: str, entry_id: str) -> bool:
        spec = self.specs[queue]
        return bool(await self.vk.xdel(spec.dead_key, entry_id))

    async def retry(self, queue: str, entry_id: str) -> bool:
        """Вернуть задачу в рабочую очередь и убрать её из DLQ."""
        spec = self.specs[queue]
        data = await self._entry(spec, entry_id)
        if data is None:
            return False

        if spec.kind == "outbox":
            task_id = data.get("task_id")
            dedup_key = data.get("dedup_key") or data.get("member")
            if self.s is not None and (task_id or dedup_key):
                from sqlalchemy import update
                from models.scheduled_tasks import ScheduledTaskModel

                cond = (
                    ScheduledTaskModel.id == int(task_id)
                    if task_id and str(task_id).isdigit()
                    else ScheduledTaskModel.dedup_key == dedup_key
                )
                await self.s.execute(
                    update(ScheduledTaskModel)
                    .where(cond)
                    .values(
                        status="pending",
                        attempts=0,
                        run_at=utc_now(),
                        locked_until=None,
                        last_error=None,
                        version=ScheduledTaskModel.version + 1,
                        updated_at=utc_now(),
                    )
                )
            elif task_id and data.get("task_kind"):
                payload = {
                    "task_id": str(task_id),
                    "task_kind": str(data["task_kind"]),
                    "ref_id": str(data.get("ref_id") or ""),
                    "version": str(data.get("version") or "1"),
                }
                await self.vk.xadd(
                    spec.target_key,
                    sign_fields(self.cfg.BUS_SIGNING_KEY, payload),
                    maxlen=10000,
                    approximate=True,
                )
            else:
                member = data.get("member")
                if not member:
                    return False
                await self.vk.zadd(self.cfg.BILLING_QUEUE_KEY, {member: utc_now().timestamp()})
                await self._clear_billing_attempts(member)
        elif spec.kind == "zset":
            member = data.get("member")
            if not member:
                return False
            await self.vk.zadd(spec.target_key, {member: utc_now().timestamp()})
            await self._clear_billing_attempts(member)
        else:
            # ts/sig пересобираем: исходная метка времени давно вне
            # anti-replay-окна, задача была бы отклонена как просроченная.
            payload = {
                k: v
                for k, v in data.items()
                if k not in ("ts", "sig", "attempts", "reason")
            }
            await self.vk.xadd(
                spec.target_key,
                sign_fields(self.cfg.BUS_SIGNING_KEY, payload),
                maxlen=self.cfg.MEDIA_TASK_STREAM_MAXLEN,
                approximate=True,
            )

        await self.vk.xdel(spec.dead_key, entry_id)
        log.info("dlq: retried %s entry %s", queue, entry_id)
        return True

    async def _clear_billing_attempts(self, member: str) -> None:
        """Сбросить счётчик попыток, иначе задача сразу уйдёт обратно в DLQ."""
        prefix, _, ref = member.partition(":")
        if prefix == "svc" and ref:
            await clear_attempts(self.vk, f"svc:action:{ref}")


def _s(value) -> str:
    return value.decode() if isinstance(value, bytes) else str(value)


__all__ = ["DLQ_QUEUES", "DeadLetters"]
