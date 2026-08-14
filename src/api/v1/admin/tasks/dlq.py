"""Админ: мёртвые очереди (DLQ) фоновых задач.

Задачи, исчерпавшие попытки, складываются в Valkey-стримы (`billing:queue:dead`,
`media:tasks:dead`, `media:results:dead`), но до сих пор их никто не читал: у
услуг молча ломалось истечение, а у медиа — конвертация (см. AUDIT.md §2.3).
Здесь — просмотр и ручной повтор.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
import valkey.asyncio as valkey

from core.config import AppConfig
from dependencies.rbac import require_perm
from dependencies.valkey import get_valkey_client
from models.user import UserModel
from services.audit import audit
from services.dlq import DLQ_QUEUES, DeadLetters
from dependencies.db import get_db_session
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


def _dlq(request: Request, vk: valkey.Valkey) -> DeadLetters:
    cfg: AppConfig = request.app.state.settings
    return DeadLetters(vk, cfg)


@router.get(
    "",
    dependencies=[Depends(require_perm("system.tasks.dlq.read"))],
    summary="Dead-letter queues",
    description="Задачи, исчерпавшие попытки, по каждой мёртвой очереди: "
    "длина и последние записи.",
)
async def list_dead_letters(
    request: Request,
    limit: int = Query(default=50, ge=1, le=500),
    vk: valkey.Valkey = Depends(get_valkey_client),
) -> dict:
    return await _dlq(request, vk).overview(limit)


@router.post(
    "/{queue}/{entry_id}/retry",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Retry a dead-lettered task",
    description="Возвращает задачу в рабочую очередь и удаляет её из DLQ. "
    "Счётчик попыток сбрасывается.",
)
async def retry_dead_letter(
    request: Request,
    queue: str,
    entry_id: str,
    vk: valkey.Valkey = Depends(get_valkey_client),
    session: AsyncSession = Depends(get_db_session),
    caller: UserModel = Depends(require_perm("system.tasks.dlq.retry")),
) -> None:
    if queue not in DLQ_QUEUES:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown queue")
    if not await _dlq(request, vk).retry(queue, entry_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "entry not found")
    await audit(
        session,
        action="tasks.dlq.retry",
        actor_id=caller.id,
        actor_role=caller.role.name if caller.role else None,
        target_type="dlq",
        target_id=f"{queue}:{entry_id}",
        ip=request.client.host if request.client else None,
    )
    await session.commit()


@router.delete(
    "/{queue}/{entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Drop a dead-lettered task",
    description="Удаляет запись из DLQ без повтора (задача признана неактуальной).",
)
async def drop_dead_letter(
    request: Request,
    queue: str,
    entry_id: str,
    vk: valkey.Valkey = Depends(get_valkey_client),
    session: AsyncSession = Depends(get_db_session),
    caller: UserModel = Depends(require_perm("system.tasks.dlq.retry")),
) -> None:
    if queue not in DLQ_QUEUES:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown queue")
    if not await _dlq(request, vk).drop(queue, entry_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "entry not found")
    await audit(
        session,
        action="tasks.dlq.drop",
        actor_id=caller.id,
        actor_role=caller.role.name if caller.role else None,
        target_type="dlq",
        target_id=f"{queue}:{entry_id}",
        ip=request.client.host if request.client else None,
    )
    await session.commit()


__all__ = ["router"]
