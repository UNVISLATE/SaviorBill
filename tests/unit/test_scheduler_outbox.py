from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.billing_consumer import BillingTaskConsumer
from services.scheduler_outbox import (
    cancel_service_expire,
    schedule_service_expire,
)
from utils.datetime_utils import utc_now

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_outbox_schedule_and_cancel_fallback_session() -> None:
    existing = None

    session = MagicMock()
    session.get_bind = MagicMock(return_value=None)
    session.scalar = AsyncMock(return_value=existing)
    added = []
    session.add = MagicMock(side_effect=lambda obj: added.append(obj))
    session.execute = AsyncMock()

    run_at = utc_now() + timedelta(days=30)
    await schedule_service_expire(session, 42, run_at)
    assert len(added) == 1
    assert added[0].dedup_key == "svc:42"
    assert added[0].task_kind == "svc_expire"
    assert added[0].ref_id == 42

    await cancel_service_expire(session, 42)
    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_consumer_ignores_stale_version() -> None:
    cfg = SimpleNamespace(
        BILLING_CONCURRENCY=2,
        BILLING_READY_STREAM="billing:tasks:ready",
        BILLING_READY_GROUP="billingexecutors",
        BILLING_QUEUE_DLQ="billing:queue:dead",
    )
    task = SimpleNamespace(
        id=10,
        dedup_key="svc:10",
        task_kind="svc_expire",
        ref_id=10,
        status="dispatched",
        version=2,  # уже перепланирована
        attempts=0,
        max_attempts=5,
        locked_until=None,
        last_error=None,
        updated_at=None,
    )
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=task)
    ctx = AsyncMock()
    ctx.__aenter__.return_value = session
    ctx.__aexit__.return_value = None
    sm = MagicMock(return_value=ctx)

    consumer = BillingTaskConsumer(sm, AsyncMock(), cfg)
    consumer._dispatch_kind = AsyncMock()

    await consumer.handle_message({"task_id": "10", "task_kind": "svc_expire", "version": "1"})
    consumer._dispatch_kind.assert_not_awaited()
    assert task.status == "dispatched"


@pytest.mark.asyncio
async def test_consumer_marks_done_and_enqueues_media_delete_post_commit() -> None:
    cfg = SimpleNamespace(
        BILLING_CONCURRENCY=2,
        BILLING_READY_STREAM="billing:tasks:ready",
        BILLING_READY_GROUP="billingexecutors",
        BILLING_QUEUE_DLQ="billing:queue:dead",
    )
    task = SimpleNamespace(
        id=11,
        dedup_key="med:55",
        task_kind="med_expire",
        ref_id=55,
        status="dispatched",
        version=1,
        attempts=0,
        max_attempts=5,
        locked_until=None,
        last_error=None,
        updated_at=None,
    )
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=task)
    ctx = AsyncMock()
    ctx.__aenter__.return_value = session
    ctx.__aexit__.return_value = None
    sm = MagicMock(return_value=ctx)

    consumer = BillingTaskConsumer(sm, AsyncMock(), cfg)
    media_bus = SimpleNamespace(enqueue_delete=AsyncMock())
    consumer.executor.media_bus = MagicMock(return_value=media_bus)
    consumer._dispatch_kind = AsyncMock(return_value=[("fs", ["a/b.webp"])])

    await consumer.handle_message({"task_id": "11", "task_kind": "med_expire", "version": "1"})
    assert task.status == "done"
    session.commit.assert_awaited_once()
    media_bus.enqueue_delete.assert_awaited_once_with("fs", ["a/b.webp"])
