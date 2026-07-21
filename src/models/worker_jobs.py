"""Единая state machine статусов асинхронных задач воркеров (WorkerJobModel).

Сейчас используется для медиа-конвейера (mediaworker: convert/preview_add/
thumb_replace) — единственного места, где реально существует протяжённый во
времени, межпроцессный жизненный цикл задачи (queued → processing →
ready/failed/stale), который стоит наблюдать из одной таблицы вместо
нескольких Valkey-источников с разным «сроком годности».

lua-задачи (`LuaBus.call`) сюда намеренно не пишутся: это синхронный
RPC-вызов в рамках одного HTTP-запроса/тика billing_loop — к моменту
возврата `call()` результат уже известен вызывающему коду, отдельная
персистентная state machine не добавляет наблюдаемости, только лишнюю
нагрузку на БД на каждый вызов. Для lua остаётся Valkey `TaskLog`
(`tasklog:lua`) — этого достаточно для короткоживущих фактов.

Valkey (`media:status:*`) остаётся быстрым кэшем для клиента/WS; эта таблица
— authoritative источник для REST-статусов (не протухает, переживает
рестарт Valkey, консистентна между списком и отдельной джобой).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    func,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from models import Base
from models.system_media import SystemMediaModel
from utils.datetime_utils import utc_now

# Терминальные состояния — job больше не будет менять статус сама по себе
# (только новый job с тем же subject_key/op может её "заменить" в выборках).
TERMINAL_STATES = ("ready", "failed", "cancelled")
ALL_STATES = ("queued", "processing", "retrying", "ready", "failed", "stale", "cancelled")


class WorkerJobModel(Base):
    """Одна задача воркера (media на сегодня; kind оставлен общим на будущее)."""

    __tablename__ = "worker_jobs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # media | lua
    op: Mapped[str] = mapped_column(String(32), nullable=False)
    subject_key: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(
        String(16), default="queued", server_default="queued", nullable=False
    )
    attempt: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1", nullable=False
    )
    worker_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_worker_jobs_kind_subject", "kind", "subject_key"),
        Index("ix_worker_jobs_state", "state"),
    )


class WorkerJobEventModel(Base):
    """Append-only история переходов состояния одной задачи."""

    __tablename__ = "worker_job_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("worker_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(16), nullable=False)
    data: Mapped[dict] = mapped_column(
        JSON, default=dict, server_default="{}", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_worker_job_events_job_created", "job_id", "created_at"),
    )


class WorkerJobsMngr:
    """Запись/чтение state machine задач воркеров."""

    def __init__(self, session: AsyncSession) -> None:
        self.s = session

    async def by_id(self, job_id: int) -> WorkerJobModel | None:
        return await self.s.get(WorkerJobModel, job_id)

    async def latest(self, kind: str, subject_key: str, op: str | None = None) -> WorkerJobModel | None:
        """Последняя (по id) задача для предмета — то, что должны показывать
        и «статус конкретной джобы», и строка в списке."""
        q = (
            select(WorkerJobModel)
            .where(WorkerJobModel.kind == kind, WorkerJobModel.subject_key == subject_key)
        )
        if op is not None:
            q = q.where(WorkerJobModel.op == op)
        q = q.order_by(WorkerJobModel.id.desc()).limit(1)
        return await self.s.scalar(q)

    async def list_recent(
        self, *, kind: str | None = None, state: str | None = None, limit: int = 100
    ) -> list[WorkerJobModel]:
        q = select(WorkerJobModel)
        if kind is not None:
            q = q.where(WorkerJobModel.kind == kind)
        if state is not None:
            q = q.where(WorkerJobModel.state == state)
        q = q.order_by(WorkerJobModel.id.desc()).limit(limit)
        return list(await self.s.scalars(q))

    async def events_for(self, job_id: int, limit: int = 200) -> list[WorkerJobEventModel]:
        rows = await self.s.scalars(
            select(WorkerJobEventModel)
            .where(WorkerJobEventModel.job_id == job_id)
            .order_by(WorkerJobEventModel.created_at.desc())
            .limit(limit)
        )
        return list(rows)

    async def _record_event(self, job_id: int, event_type: str, data: dict | None = None) -> None:
        self.s.add(WorkerJobEventModel(job_id=job_id, event_type=event_type, data=data or {}))
        await self.s.flush()

    async def apply(
        self,
        *,
        kind: str,
        op: str,
        subject_key: str,
        state: str,
        worker_id: str | None = None,
        error: str | None = None,
        event_data: dict | None = None,
    ) -> WorkerJobModel:
        """Применить событие state-машины: создать новую джобу (state=="queued")
        либо обновить существующую активную (не в терминальном состоянии).

        Идемпотентно относительно повторной доставки: если для (kind, op,
        subject_key) уже есть незавершённая джоба — она обновляется, новая
        не создаётся (важно для at-least-once доставки Valkey Streams).
        """
        current = await self.latest(kind, subject_key, op)
        if current is None or current.state in TERMINAL_STATES:
            if state == "queued" or current is None:
                current = WorkerJobModel(
                    kind=kind, op=op, subject_key=subject_key, state="queued"
                )
                self.s.add(current)
                await self.s.flush()
            else:
                # Событие "processing/ready/..." без предшествующего queued
                # (например, при перезапуске consumer-группы) — заводим
                # новую джобу сразу в этом состоянии, чтобы не потерять факт.
                current = WorkerJobModel(kind=kind, op=op, subject_key=subject_key, state=state)
                self.s.add(current)
                await self.s.flush()
        current.state = state
        current.worker_id = worker_id or current.worker_id
        current.error = error
        now = utc_now()
        if state == "processing" and current.started_at is None:
            current.started_at = now
        if state in TERMINAL_STATES:
            current.finished_at = now
        if state == "retrying":
            current.attempt += 1
        await self.s.flush()
        await self._record_event(current.id, state, event_data)
        return current

    async def active_for_owner(self, owner_id: int, *, kind: str = "media") -> list[WorkerJobModel]:
        """Активные (не терминальные) джобы владельца — восстановление карточек
        "в обработке" после перезагрузки страницы (см. IMPLEMENTATION_PLAN.md
        §3.Д). ``subject_key`` в ``worker_jobs`` — это ``system_media.token``
        (миграция под ``owner_id`` в самой таблице джоб не добавлялась —
        джойним на ``system_media`` вместо денормализации)."""
        q = (
            select(WorkerJobModel)
            .join(SystemMediaModel, SystemMediaModel.token == WorkerJobModel.subject_key)
            .where(
                WorkerJobModel.kind == kind,
                WorkerJobModel.state.in_(("queued", "processing", "retrying")),
                SystemMediaModel.owner_id == owner_id,
            )
            .order_by(WorkerJobModel.id.desc())
        )
        return list(await self.s.scalars(q))

    async def count_pending(self, kind: str) -> int:
        """Число задач в queued/processing/retrying — для метрики ``worker_jobs_pending``."""
        result = await self.s.execute(
            select(func.count()).where(
                WorkerJobModel.kind == kind,
                WorkerJobModel.state.in_(("queued", "processing", "retrying")),
            )
        )
        return int(result.scalar_one())

    async def sweep_stale(self, older_than: timedelta) -> int:
        """Пометить `stale` задачи, застрявшие в processing дольше порога.

        Отдельный от Stream-level reclaim (§3.1) механизм — тот работает на
        уровне доставки сообщения консьюмеру, этот — на уровне бизнес-статуса
        (воркер мог быть жив, честно взял задачу и потом упал без единого
        сигнала billing-стороне)."""
        cutoff = utc_now() - older_than
        rows = await self.s.scalars(
            select(WorkerJobModel).where(
                WorkerJobModel.state == "processing",
                WorkerJobModel.updated_at < cutoff,
            )
        )
        n = 0
        for job in rows:
            job.state = "stale"
            job.error = job.error or "no update from worker within timeout"
            await self._record_event(job.id, "stale")
            n += 1
        if n:
            await self.s.flush()
        return n


__all__ = [
    "WorkerJobModel",
    "WorkerJobEventModel",
    "WorkerJobsMngr",
    "TERMINAL_STATES",
    "ALL_STATES",
]
