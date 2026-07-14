"""Админ: базовая аналитика (/api/v1/admin/analytics/basic).

Простые SQL-агрегаты по промокодам/платежам/услугам. Право
``analytics.basic.read`` (см. IMPLEMENTATION_PLAN §13.1) — общее для чтения
всех сводок и топ-листов этого уровня (действие одно и то же: просмотр
готовых отчётов, ничего не меняет).
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query

from analytics.basic import BasicAnalytics
from dependencies.db import get_db_session
from dependencies.rbac import require_perm
from schemas.analytics import (
    PaymentsSummary,
    ProviderRevenue,
    PromoCodeStat,
    PromoSummary,
    ServiceSales,
)
from schemas.page import Page
from sqlalchemy.ext.asyncio import AsyncSession
from utils.pagination import PageParams, page_params, paginate, paginate_rows

router = APIRouter(
    prefix="/analytics/basic",
    dependencies=[Depends(require_perm("analytics.basic.read"))],
)


def _mngr(session: AsyncSession = Depends(get_db_session)) -> BasicAnalytics:
    return BasicAnalytics(session)


@router.get("/promo", response_model=PromoSummary, summary="Promo summary")
async def promo_summary(mngr: BasicAnalytics = Depends(_mngr)) -> PromoSummary:
    total = await mngr.promo_summary()
    return PromoSummary(total_redemptions=total)


@router.get(
    "/promo/top",
    response_model=Page[PromoCodeStat],
    summary="Top promo codes",
)
async def promo_top(
    pp: PageParams = Depends(page_params),
    mngr: BasicAnalytics = Depends(_mngr),
) -> Page[PromoCodeStat]:
    items, total, has_more = await paginate(
        mngr.s,
        mngr.promo_top_stmt(),
        mngr.promo_code_row,
        limit=pp.limit,
        offset=pp.offset,
    )
    return Page(
        items=[PromoCodeStat(**i) for i in items],
        total=total,
        limit=pp.limit,
        offset=pp.offset,
        has_more=has_more,
    )


@router.get(
    "/payments", response_model=PaymentsSummary, summary="Payment revenue and statuses"
)
async def payments_summary(
    since: datetime | None = Query(None, description="Period start"),
    until: datetime | None = Query(None, description="Period end"),
    mngr: BasicAnalytics = Depends(_mngr),
) -> PaymentsSummary:
    data = await mngr.payments_summary(since=since, until=until)
    return PaymentsSummary(**data)


@router.get(
    "/payments/by-provider",
    response_model=Page[ProviderRevenue],
    summary="Revenue by provider",
)
async def payments_by_provider(
    since: datetime | None = Query(None, description="Period start"),
    until: datetime | None = Query(None, description="Period end"),
    pp: PageParams = Depends(page_params),
    mngr: BasicAnalytics = Depends(_mngr),
) -> Page[ProviderRevenue]:
    stmt = mngr.provider_revenue_stmt(since=since, until=until)
    items, total, has_more = await paginate_rows(
        mngr.s, stmt, mngr.provider_revenue_row, limit=pp.limit, offset=pp.offset
    )
    return Page(
        items=[ProviderRevenue(**i) for i in items],
        total=total,
        limit=pp.limit,
        offset=pp.offset,
        has_more=has_more,
    )


@router.get(
    "/services/top",
    response_model=Page[ServiceSales],
    summary="Top services and key stock",
)
async def services_top(
    pp: PageParams = Depends(page_params),
    mngr: BasicAnalytics = Depends(_mngr),
) -> Page[ServiceSales]:
    stmt = mngr.service_sales_stmt()
    items, total, has_more = await paginate_rows(
        mngr.s, stmt, mngr.service_sales_row, limit=pp.limit, offset=pp.offset
    )
    # Остаток ключей — отдельный запрос на услугу (см. docstring service_sales_stmt).
    for item in items:
        item["remaining_keys"] = await mngr.remaining_keys_for(item["service_id"])
    return Page(
        items=[ServiceSales(**i) for i in items],
        total=total,
        limit=pp.limit,
        offset=pp.offset,
        has_more=has_more,
    )


__all__ = ["router"]
