"""Сервис записи в аудит-журнал финансовых и административных действий."""

from __future__ import annotations

import contextvars
from typing import TYPE_CHECKING
from sqlalchemy.ext.asyncio import AsyncSession

from models.audit_log import AuditLogModel

if TYPE_CHECKING:
    from models.app_tokens import AppTokenModel

current_app_token_ctx: contextvars.ContextVar[AppTokenModel | None] = contextvars.ContextVar(
    "current_app_token", default=None
)
current_client_ip_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_client_ip", default=None
)


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
    Если действие выполнено через App Token, автоматически обогащает запись
    префиксом токена, IP и именем приложения.
    """
    entry_meta = dict(meta) if meta else {}

    active_app_token = current_app_token_ctx.get()
    if active_app_token is not None:
        actor_role = f"app_token:{active_app_token.token_prefix}"
        entry_meta["app_token_prefix"] = active_app_token.token_prefix
        entry_meta["app_token_name"] = active_app_token.name
        if ip is None:
            ip = current_client_ip_ctx.get()

    if ip is None:
        ip = current_client_ip_ctx.get()

    entry = AuditLogModel(
        action=action,
        actor_account_id=actor_id,
        actor_role=actor_role,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        ip=ip,
        result=result,
        meta=entry_meta,
    )
    session.add(entry)
    await session.flush()


__all__ = ["audit", "current_app_token_ctx", "current_client_ip_ctx"]
