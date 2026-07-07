"""Админ: просмотр аудит-журнала (/api/v1/admin/audit).

Только чтение (append-only журнал). Требует право ``audit.read``. Поддерживает
фильтрацию по действию/актору и пагинацию.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.db import get_db_session
from dependencies.rbac import require_perm
from models.audit_log import AuditLogModel
from schemas.audit import AuditEntry
from schemas.page import Page
from utils.pagination import PageParams, page_params, paginate

router = APIRouter()


@router.get(
    "/audit",
    response_model=Page[AuditEntry],
    dependencies=[Depends(require_perm("audit.read"))],
    summary="Аудит-журнал",
    description=(
        "Постраничный просмотр append-only журнала аудита. Опциональные фильтры: по действию (`action`) и актору "
        "(`actor_account_id`)."
    ),
)
async def list_audit(
    action: str | None = Query(None, description="Фильтр по действию (опционально)"),
    actor_account_id: int | None = Query(
        None, ge=0, description="Фильтр по актору (опционально)"
    ),
    pp: PageParams = Depends(page_params),
    session: AsyncSession = Depends(get_db_session),
) -> Page[AuditEntry]:
    stmt = select(AuditLogModel).order_by(AuditLogModel.id.desc())
    if action:
        stmt = stmt.where(AuditLogModel.action == action)
    if actor_account_id is not None:
        stmt = stmt.where(AuditLogModel.actor_account_id == actor_account_id)
    items, total, has_more = await paginate(
        session, stmt, AuditEntry.from_model, limit=pp.limit, offset=pp.offset
    )
    return Page(
        items=items, total=total, limit=pp.limit, offset=pp.offset, has_more=has_more
    )


__all__ = ["router"]
