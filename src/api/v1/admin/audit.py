"""Админ: просмотр аудит-журнала (/api/v1/admin/audit).

Только чтение (append-only журнал). Требует право ``audit.read``. Поддерживает
фильтрацию по действию/актору/дате и пагинацию.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.db import get_db_session
from dependencies.rbac import require_perm
from models.audit_log import AuditLogModel
from schemas.audit import AuditEntry
from schemas.page import Page
from utils.pagination import (
    PageParams,
    apply_sort,
    page_params,
    paginate_search,
    q_param,
    sort_param,
)

router = APIRouter()

_AUDIT_SORT_FIELDS = {"id", "ts", "action", "target_type", "actor_account_id"}


@router.get(
    "",
    response_model=Page[AuditEntry],
    dependencies=[Depends(require_perm("audit.read"))],
    summary="Audit log",
    description="Paginated audit log with optional action/actor/date-range "
    "filters. `q` searches action/target_type/target_id (exact substring, "
    f"no fuzzy); `sort` accepts {'/'.join(sorted(_AUDIT_SORT_FIELDS))}.",
)
async def list_audit(
    action: str | None = Query(None, description="Action filter"),
    actor_account_id: int | None = Query(None, ge=0, description="Actor filter"),
    since: datetime | None = Query(
        None, description="Only entries at/after this timestamp (inclusive)"
    ),
    until: datetime | None = Query(
        None, description="Only entries before this timestamp (exclusive)"
    ),
    q: str | None = Depends(q_param),
    sort: str | None = Depends(sort_param),
    pp: PageParams = Depends(page_params),
    session: AsyncSession = Depends(get_db_session),
) -> Page[AuditEntry]:
    stmt = apply_sort(select(AuditLogModel), AuditLogModel, sort, _AUDIT_SORT_FIELDS)
    if sort is None:
        stmt = stmt.order_by(AuditLogModel.id.desc())
    if action:
        stmt = stmt.where(AuditLogModel.action == action)
    if actor_account_id is not None:
        stmt = stmt.where(AuditLogModel.actor_account_id == actor_account_id)
    if since is not None:
        stmt = stmt.where(AuditLogModel.ts >= since)
    if until is not None:
        stmt = stmt.where(AuditLogModel.ts < until)
    items, total, has_more = await paginate_search(
        session,
        stmt,
        AuditLogModel,
        AuditEntry.from_model,
        limit=pp.limit,
        offset=pp.offset,
        q=q,
        search_fields=("action", "target_type", "target_id"),
    )
    return Page(
        items=items, total=total, limit=pp.limit, offset=pp.offset, has_more=has_more
    )


__all__ = ["router"]
