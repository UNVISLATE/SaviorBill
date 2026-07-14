"""Схемы ответов модуля аналитики (basic + advanced)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

# ─────────────────────────────────────────────────────────────────────────────
# Basic (простые SQL-агрегаты)
# ─────────────────────────────────────────────────────────────────────────────


class PromoSummary(BaseModel):
    """Promo redemption summary."""

    total_redemptions: int = Field(description="Total redemptions")


class PromoCodeStat(BaseModel):
    """Promo code stats."""

    id: int
    code: str
    catalog_id: int
    used_count: int
    max_uses: int | None
    remaining: int | None = Field(description="Remaining activations; null = unlimited")


class PaymentsSummary(BaseModel):
    """Payment summary for period."""

    period_from: datetime | None
    period_to: datetime | None
    revenue: Decimal = Field(description="Paid revenue")
    paid_count: int
    failed_count: int
    refunded_count: int
    pending_count: int


class ProviderRevenue(BaseModel):
    """Revenue by payment provider."""

    provider: str
    revenue: Decimal
    count: int


class ServiceSales(BaseModel):
    """Service sales summary."""

    service_id: int
    name: str
    sold: int = Field(description="Sold units")
    remaining_keys: int | None = Field(
        description="Remaining digital keys; null = not key delivery"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Advanced (Polars): LTV / retention / churn / ROI
# ─────────────────────────────────────────────────────────────────────────────


class AccountLTV(BaseModel):
    """Account lifetime value."""

    account_id: int
    ltv: Decimal


class RetentionCohort(BaseModel):
    """Retention cohort."""

    cohort: str = Field(description="Cohort label")
    cohort_size: int
    retention: list[float] = Field(description="Retention by period")


class ChurnStats(BaseModel):
    """Churn summary."""

    inactive_days: int
    churn_rate: float = Field(description="Rate from 0 to 1")
    total_accounts: int
    churned_accounts: int


class RoiStats(BaseModel):
    """ROI availability."""

    available: bool = False
    reason: str = (
        "нет данных о стоимости привлечения (CAC) в модели — добавить "
        "источник расходов на маркетинг, чтобы включить расчёт"
    )


class AdvancedSummary(BaseModel):
    """Advanced analytics summary."""

    avg_days_to_first_payment: float | None
    churn: ChurnStats
    roi: RoiStats


__all__ = [
    "PromoSummary",
    "PromoCodeStat",
    "PaymentsSummary",
    "ProviderRevenue",
    "ServiceSales",
    "AccountLTV",
    "RetentionCohort",
    "ChurnStats",
    "RoiStats",
    "AdvancedSummary",
]
