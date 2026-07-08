"""Продвинутый уровень аналитики (Polars): LTV, retention, churn, ROI-заглушка.

Изолирован от ORM-слоя приложения намеренно (см. IMPLEMENTATION_PLAN §13.2) —
минимум связей, чтобы в будущем можно было вынести в отдельный процесс/сервис
почти без переписывания. Данные из БД читаются один раз тонким слоем
(:func:`fetch_frames`) в виде списков словарей → ``polars.DataFrame``; вся
собственно аналитика — чистые функции над готовыми ``DataFrame`` (легко
юнит-тестируются синтетическими данными, без БД).

Право доступа: ``analytics.advanced.read`` — отдельное от
``analytics.basic.read`` (не наследуется), только ``owner`` по умолчанию.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

import polars as pl
import valkey.asyncio as valkey
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from enums import PayStatus
from models.user import UserModel
from models.user_payments import UserPaymentsModel
from utils.datetime_utils import utc_now

log = logging.getLogger("saviorbill.analytics.advanced")

_CACHE_KEY = "analytics:advanced:v1"


# Чистые вычисления над Polars DataFrame (юнит-тестируемые без БД)
def compute_ltv(df_payments: pl.DataFrame) -> pl.DataFrame:
    """LTV — суммарный revenue paid-платежей на аккаунт.

    :arg df_payments: колонки ``account_id``, ``amount``, ``status``.
    :return: DataFrame с колонками ``account_id``, ``ltv`` (отсортирован по убыванию).
    """
    if df_payments.is_empty():
        return pl.DataFrame({"account_id": [], "ltv": []})
    paid = df_payments.filter(pl.col("status") == PayStatus.PAID)
    if paid.is_empty():
        return pl.DataFrame({"account_id": [], "ltv": []})
    return (
        paid.group_by("account_id")
        .agg(pl.col("amount").sum().alias("ltv"))
        .sort("ltv", descending=True)
    )


def compute_retention(
    df_accounts: pl.DataFrame,
    df_activity: pl.DataFrame,
    *,
    unit: str = "week",
    periods: int = 8,
) -> pl.DataFrame:
    """Когортный retention: % аккаунтов когорты, активных на N-й период после регистрации.

    :arg df_accounts: колонки ``account_id``, ``created_at`` (datetime).
    :arg df_activity: колонки ``account_id``, ``activity_at`` (datetime) — одна
        строка на событие активности (платёж, использование услуги и т.п.).
    :arg unit: ``"day"`` или ``"week"`` — длина периода когорты/retention-окна.
    :arg periods: сколько периодов вперёд считать (0..periods включительно).
    :return: DataFrame с колонками ``cohort`` (ISO-дата начала когорты),
        ``cohort_size``, ``period_0``..``period_N`` (доля 0..1).
    """
    if df_accounts.is_empty():
        return pl.DataFrame({"cohort": [], "cohort_size": []})

    every = "1w" if unit == "week" else "1d"
    accounts = df_accounts.with_columns(
        pl.col("created_at").dt.truncate(every).alias("cohort")
    )
    cohorts = accounts.group_by("cohort").agg(pl.len().alias("cohort_size"))

    result = cohorts.clone()
    period_cols = []
    for n in range(periods + 1):
        delta = timedelta(weeks=n) if unit == "week" else timedelta(days=n)
        # Активен в период N: есть активность в [cohort_start+delta, cohort_start+delta+unit).
        joined = accounts.join(df_activity, on="account_id", how="left")
        window_start = pl.col("cohort") + delta
        window_end = window_start + (
            timedelta(weeks=1) if unit == "week" else timedelta(days=1)
        )
        active_in_period = joined.filter(
            pl.col("activity_at").is_not_null()
            & (pl.col("activity_at") >= window_start)
            & (pl.col("activity_at") < window_end)
        )
        active_counts = (
            active_in_period.group_by("cohort")
            .agg(pl.col("account_id").n_unique().alias(f"active_{n}"))
        )
        result = result.join(active_counts, on="cohort", how="left")
        col = f"period_{n}"
        result = result.with_columns(
            (pl.col(f"active_{n}").fill_null(0) / pl.col("cohort_size"))
            .alias(col)
        ).drop(f"active_{n}")
        period_cols.append(col)

    return result.sort("cohort").select(["cohort", "cohort_size", *period_cols])


def compute_churn_rate(
    df_accounts: pl.DataFrame,
    df_activity: pl.DataFrame,
    *,
    now: datetime,
    inactive_days: int = 30,
) -> dict:
    """Доля аккаунтов без активности дольше ``inactive_days``.

    :arg df_accounts: колонка ``account_id``.
    :arg df_activity: колонки ``account_id``, ``activity_at``.
    :arg now: точка отсчёта "сейчас" (для детерминированных тестов).
    :return: ``{"churn_rate", "total_accounts", "churned_accounts"}``.
    """
    total = df_accounts.height
    if total == 0:
        return {
            "churn_rate": 0.0,
            "total_accounts": 0,
            "churned_accounts": 0,
            "inactive_days": inactive_days,
        }

    cutoff = now - timedelta(days=inactive_days)
    if df_activity.is_empty():
        # Нет вообще никакой активности ни у кого — все считаются оттёкшими.
        return {
            "churn_rate": 1.0,
            "total_accounts": total,
            "churned_accounts": total,
            "inactive_days": inactive_days,
        }

    last_activity = df_activity.group_by("account_id").agg(
        pl.col("activity_at").max().alias("last_activity_at")
    )
    merged = df_accounts.join(last_activity, on="account_id", how="left")
    churned = merged.filter(
        pl.col("last_activity_at").is_null() | (pl.col("last_activity_at") < cutoff)
    ).height
    return {
        "churn_rate": churned / total,
        "total_accounts": total,
        "churned_accounts": churned,
        "inactive_days": inactive_days,
    }


def compute_avg_days_to_first_payment(
    df_accounts: pl.DataFrame, df_payments: pl.DataFrame
) -> float | None:
    """Среднее число дней от регистрации до первого paid-платежа.

    :return: ``None``, если ни у кого нет ни одного paid-платежа.
    """
    paid = df_payments.filter(pl.col("status") == PayStatus.PAID)
    if paid.is_empty() or df_accounts.is_empty():
        return None
    first_paid = paid.group_by("account_id").agg(
        pl.col("created_at").min().alias("first_paid_at")
    )
    merged = df_accounts.join(first_paid, on="account_id", how="inner")
    if merged.is_empty():
        return None
    days = (
        (merged["first_paid_at"] - merged["created_at"]).dt.total_seconds() / 86400.0
    )
    return float(days.mean())


def roi_stats() -> dict:
    """ROI — заглушка: модель данных не хранит стоимость привлечения (CAC).

    TODO: как только появится источник расходов на маркетинг/привлечение,
    посчитать ``LTV / CAC`` по когортам.
    """
    return {
        "available": False,
        "reason": (
            "нет данных о стоимости привлечения (CAC) в модели — добавить "
            "источник расходов на маркетинг, чтобы включить расчёт"
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Тонкий слой чтения из БД (не юнит-тестируется — требует интеграционного теста)
# ─────────────────────────────────────────────────────────────────────────────

async def fetch_frames(session: AsyncSession) -> dict[str, pl.DataFrame]:
    """Выгрузить нужные таблицы в Polars DataFrame одним проходом на таблицу.

    :return: ``{"accounts": df, "payments": df}`` — активность (для retention/
        churn) сейчас определяется по платежам (``payments.created_at``);
        при появлении других источников активности (использование услуг и
        т.п.) сюда добавляется объединение с ними.
    """
    acc_rows = (
        await session.execute(select(UserModel.id, UserModel.created_at))
    ).all()
    pay_rows = (
        await session.execute(
            select(
                UserPaymentsModel.account_id,
                UserPaymentsModel.amount,
                UserPaymentsModel.status,
                UserPaymentsModel.created_at,
            )
        )
    ).all()

    accounts = pl.DataFrame(
        {"account_id": [r.id for r in acc_rows], "created_at": [r.created_at for r in acc_rows]}
    )
    payments = pl.DataFrame(
        {
            "account_id": [r.account_id for r in pay_rows],
            "amount": [float(r.amount) for r in pay_rows],
            "status": [r.status for r in pay_rows],
            "created_at": [r.created_at for r in pay_rows],
        }
    )
    return {"accounts": accounts, "payments": payments}


async def get_summary(
    session: AsyncSession,
    vk: valkey.Valkey,
    *,
    cache_ttl: int = 3600,
    inactive_days: int = 30,
) -> dict:
    """Комбинированная сводка (avg days to first payment, churn, ROI-заглушка).

    Кэшируется в Valkey (``analytics:advanced:v1``, TTL ``cache_ttl``) —
    когортные расчёты недёшевы при большом объёме данных.
    """
    cached = await vk.get(_CACHE_KEY)
    if cached is not None:
        return json.loads(cached)

    frames = await fetch_frames(session)
    accounts, payments = frames["accounts"], frames["payments"]
    activity = payments.filter(pl.col("status") == PayStatus.PAID).select(
        pl.col("account_id"), pl.col("created_at").alias("activity_at")
    )

    result = {
        "avg_days_to_first_payment": compute_avg_days_to_first_payment(accounts, payments),
        "churn": compute_churn_rate(
            accounts, activity, now=utc_now(), inactive_days=inactive_days
        ),
        "roi": roi_stats(),
    }
    await vk.set(_CACHE_KEY, json.dumps(result), ex=cache_ttl)
    return result


__all__ = [
    "compute_ltv",
    "compute_retention",
    "compute_churn_rate",
    "compute_avg_days_to_first_payment",
    "roi_stats",
    "fetch_frames",
    "get_summary",
]
