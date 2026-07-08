"""Схемы ответов модуля аналитики (basic + advanced)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────────────────────
# Basic (простые SQL-агрегаты)
# ─────────────────────────────────────────────────────────────────────────────

class PromoSummary(BaseModel):
    """Сводка по погашениям промокодов."""

    total_redemptions: int = Field(description="Всего погашений по всем кодам")


class PromoCodeStat(BaseModel):
    """Статистика по одному промокоду (для топа по использованию)."""

    id: int
    code: str
    catalog_id: int
    used_count: int
    max_uses: int | None
    remaining: int | None = Field(
        description="Осталось активаций (null — безлимитный код)"
    )


class PaymentsSummary(BaseModel):
    """Сводка по платежам за период."""

    period_from: datetime | None
    period_to: datetime | None
    revenue: Decimal = Field(description="Сумма paid-платежей за период")
    paid_count: int
    failed_count: int
    refunded_count: int
    pending_count: int


class ProviderRevenue(BaseModel):
    """Разбивка revenue по платёжному провайдеру."""

    provider: str
    revenue: Decimal
    count: int


class ServiceSales(BaseModel):
    """Продажи услуги + остаток цифровых ключей (если применимо)."""

    service_id: int
    name: str
    sold: int = Field(description="Число выданных экземпляров (не pending/failed/cancelled)")
    remaining_keys: int | None = Field(
        description="Остаток непроданных цифровых ключей (null — не key-доставка)"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Advanced (Polars): LTV / retention / churn / ROI
# ─────────────────────────────────────────────────────────────────────────────

class AccountLTV(BaseModel):
    """Суммарный revenue (LTV) одного аккаунта."""

    account_id: int
    ltv: Decimal


class RetentionCohort(BaseModel):
    """Одна когорта (по неделе/дню регистрации) и её retention по периодам."""

    cohort: str = Field(description="Метка когорты (дата начала периода, ISO)")
    cohort_size: int
    retention: list[float] = Field(
        description="Доля активных на конец каждого периода 0..N (0 = сама когорта)"
    )


class ChurnStats(BaseModel):
    """Доля аккаунтов, неактивных дольше порога."""

    inactive_days: int
    churn_rate: float = Field(description="Доля от 0 до 1")
    total_accounts: int
    churned_accounts: int


class RoiStats(BaseModel):
    """ROI — заглушка: в модели данных нет стоимости привлечения (CAC)."""

    available: bool = False
    reason: str = (
        "нет данных о стоимости привлечения (CAC) в модели — добавить "
        "источник расходов на маркетинг, чтобы включить расчёт"
    )


class AdvancedSummary(BaseModel):
    """Комбинированная сводка продвинутой аналитики (кэшируется в Valkey)."""

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
