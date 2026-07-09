"""Админ: продвинутая аналитика (/api/v1/admin/analytics/advanced), Polars.

Право ``analytics.advanced.read`` — **отдельное** от ``analytics.basic.read``
(не наследуется), по умолчанию только у ``owner`` (см. IMPLEMENTATION_PLAN
§13.2/13.3 — явное решение под будущую монетизацию продвинутого уровня).
"""

from __future__ import annotations

import polars as pl
import valkey.asyncio as valkey
from fastapi import APIRouter, Depends, Query

from analytics.advanced import compute_retention, fetch_frames, get_summary
from dependencies.db import get_db_session
from dependencies.rbac import require_perm
from dependencies.settings import SystemSettingsMngr, get_settings_mngr
from dependencies.valkey import get_valkey_client
from enums import PayStatus
from schemas.analytics import AdvancedSummary, RetentionCohort
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(
    prefix="/analytics/advanced",
    dependencies=[Depends(require_perm("analytics.advanced.read"))],
)


@router.get(
    "/summary",
    response_model=AdvancedSummary,
    summary="Advanced summary",
)
async def advanced_summary(
    session: AsyncSession = Depends(get_db_session),
    vk: valkey.Valkey = Depends(get_valkey_client),
    settings: SystemSettingsMngr = Depends(get_settings_mngr),
) -> AdvancedSummary:
    ttl = await settings.get_int("analytics.advanced.cache_ttl_sec", 3600)
    inactive_days = await settings.get_int("analytics.churn.inactive_days", 30)
    data = await get_summary(
        session, vk, cache_ttl=ttl or 3600, inactive_days=inactive_days or 30
    )
    return AdvancedSummary(**data)


@router.get(
    "/retention",
    response_model=list[RetentionCohort],
    summary="Retention cohorts",
)
async def retention(
    unit: str = Query("week", pattern="^(day|week)$", description="Cohort unit"),
    periods: int = Query(8, ge=1, le=52, description="Periods to calculate"),
    session: AsyncSession = Depends(get_db_session),
) -> list[RetentionCohort]:
    frames = await fetch_frames(session)
    accounts, payments = frames["accounts"], frames["payments"]
    activity = payments.filter(pl.col("status") == PayStatus.PAID).select(
        pl.col("account_id"), pl.col("created_at").alias("activity_at")
    )
    df = compute_retention(accounts, activity, unit=unit, periods=periods)
    period_cols = [c for c in df.columns if c.startswith("period_")]
    return [
        RetentionCohort(
            cohort=str(row["cohort"]),
            cohort_size=row["cohort_size"],
            retention=[row[c] for c in period_cols],
        )
        for row in df.to_dicts()
    ]


__all__ = ["router"]
