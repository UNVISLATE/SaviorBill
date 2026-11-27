"""Transactional Outbox клиент для таблицы ``scheduled_tasks`` (Go-планировщик ``scheduler``)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from models.scheduled_tasks import ScheduledTaskModel
from utils.datetime_utils import utc_now

_ACTIVE_STATUSES = ("pending", "dispatched", "processing")


class ScheduledTasksMngr:
    """Управление отложенными задачами внутри текущей транзакции SQLAlchemy."""

    def __init__(self, session: AsyncSession) -> None:
        self.s = session

    def _is_postgres(self) -> bool:
        bind = self.s.get_bind()
        return bind is not None and bind.dialect.name == "postgresql"

    async def upsert(
        self,
        *,
        dedup_key: str,
        task_kind: str,
        ref_id: int | None,
        run_at: datetime,
        payload: dict[str, Any] | None = None,
        max_attempts: int = 5,
    ) -> None:
        """Создать или перенести активную задачу по ``dedup_key`` в той же транзакции."""
        now = utc_now()
        body = dict(payload or {})
        if self._is_postgres():
            stmt = pg_insert(ScheduledTaskModel).values(
                dedup_key=dedup_key,
                task_kind=task_kind,
                ref_id=ref_id,
                payload=body,
                run_at=run_at,
                status="pending",
                attempts=0,
                max_attempts=max_attempts,
                locked_until=None,
                last_error=None,
                version=1,
                created_at=now,
                updated_at=now,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["dedup_key"],
                index_where=text(
                    "dedup_key IS NOT NULL AND status IN ('pending', 'dispatched', 'processing')"
                ),
                set_={
                    "task_kind": task_kind,
                    "ref_id": ref_id,
                    "payload": body,
                    "run_at": run_at,
                    "status": "pending",
                    "locked_until": None,
                    "last_error": None,
                    "version": ScheduledTaskModel.version + 1,
                    "updated_at": now,
                },
            )
            await self.s.execute(stmt)
            return

        # Fallback для SQLite/mock-сессий в unit-тестах.
        existing = await self.s.scalar(
            select(ScheduledTaskModel)
            .where(
                ScheduledTaskModel.dedup_key == dedup_key,
                ScheduledTaskModel.status.in_(_ACTIVE_STATUSES),
            )
            .limit(1)
        )
        if existing is not None:
            existing.task_kind = task_kind
            existing.ref_id = ref_id
            existing.payload = body
            existing.run_at = run_at
            existing.status = "pending"
            existing.locked_until = None
            existing.last_error = None
            existing.version = (existing.version or 1) + 1
            existing.updated_at = now
        else:
            self.s.add(
                ScheduledTaskModel(
                    dedup_key=dedup_key,
                    task_kind=task_kind,
                    ref_id=ref_id,
                    payload=body,
                    run_at=run_at,
                    status="pending",
                    attempts=0,
                    max_attempts=max_attempts,
                    version=1,
                    created_at=now,
                    updated_at=now,
                )
            )

    async def cancel(self, dedup_key: str) -> None:
        """Отменить активную задачу по ``dedup_key``."""
        await self.s.execute(
            update(ScheduledTaskModel)
            .where(
                ScheduledTaskModel.dedup_key == dedup_key,
                ScheduledTaskModel.status.in_(_ACTIVE_STATUSES),
            )
            .values(
                status="cancelled",
                locked_until=None,
                version=ScheduledTaskModel.version + 1,
                updated_at=utc_now(),
            )
        )


async def schedule_service_expire(
    session: AsyncSession, usvc_id: int, run_at: datetime
) -> None:
    await ScheduledTasksMngr(session).upsert(
        dedup_key=f"svc:{usvc_id}",
        task_kind="svc_expire",
        ref_id=usvc_id,
        run_at=run_at,
    )


async def cancel_service_expire(session: AsyncSession, usvc_id: int) -> None:
    await ScheduledTasksMngr(session).cancel(f"svc:{usvc_id}")


async def schedule_provision_poll(
    session: AsyncSession, usvc_id: int, run_at: datetime
) -> None:
    await ScheduledTasksMngr(session).upsert(
        dedup_key=f"poll:{usvc_id}",
        task_kind="svc_provision_poll",
        ref_id=usvc_id,
        run_at=run_at,
    )


async def cancel_provision_poll(session: AsyncSession, usvc_id: int) -> None:
    await ScheduledTasksMngr(session).cancel(f"poll:{usvc_id}")


async def schedule_apply_config(
    session: AsyncSession, usvc_id: int, run_at: datetime
) -> None:
    await ScheduledTasksMngr(session).upsert(
        dedup_key=f"cfg:{usvc_id}",
        task_kind="svc_apply_config",
        ref_id=usvc_id,
        run_at=run_at,
    )


async def cancel_apply_config(session: AsyncSession, usvc_id: int) -> None:
    await ScheduledTasksMngr(session).cancel(f"cfg:{usvc_id}")


async def schedule_payment_recheck(
    session: AsyncSession, pay_id: int, run_at: datetime
) -> None:
    await ScheduledTasksMngr(session).upsert(
        dedup_key=f"pay:{pay_id}",
        task_kind="pay_recheck",
        ref_id=pay_id,
        run_at=run_at,
    )


async def schedule_delivery_retry(
    session: AsyncSession, usvc_id: int, run_at: datetime
) -> None:
    await ScheduledTasksMngr(session).upsert(
        dedup_key=f"dlv:{usvc_id}",
        task_kind="dlv_retry",
        ref_id=usvc_id,
        run_at=run_at,
    )


async def schedule_media_expire(
    session: AsyncSession, media_id: int, run_at: datetime
) -> None:
    await ScheduledTasksMngr(session).upsert(
        dedup_key=f"med:{media_id}",
        task_kind="med_expire",
        ref_id=media_id,
        run_at=run_at,
    )


async def cancel_media_expire(session: AsyncSession, media_id: int) -> None:
    await ScheduledTasksMngr(session).cancel(f"med:{media_id}")


__all__ = [
    "ScheduledTasksMngr",
    "schedule_service_expire",
    "cancel_service_expire",
    "schedule_payment_recheck",
    "schedule_delivery_retry",
    "schedule_media_expire",
    "cancel_media_expire",
]
