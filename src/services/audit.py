"""Сервис записи в аудит-журнал финансовых и административных действий."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from models.audit_log import AuditLogModel


async def audit(
    session: AsyncSession,
    action: str,
    actor_id: int | None = None,
    actor_role: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    ip: str | None = None,
    result: str = "ok",
    meta: dict | None = None,
) -> None:
    """Добавить запись в аудит-журнал (append-only).

    Пишется в ту же сессию, что и основное действие: коммит/откат — общие.
    """
    entry = AuditLogModel(
        action=action,
        actor_account_id=actor_id,
        actor_role=actor_role,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        ip=ip,
        result=result,
        meta=meta or {},
    )
    session.add(entry)
    await session.flush()


__all__ = ["audit"]
