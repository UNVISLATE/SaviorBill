"""Юнит-тесты продвинутой аналитики (analytics/advanced.py) — чистые функции.

Только вычисления над готовыми Polars DataFrame — без обращения к БД (сбор
данных из БД, ``fetch_frames``, требует интеграционного теста с реальным
Postgres — см. IMPLEMENTATION_PLAN §14/15).
"""

from __future__ import annotations

from datetime import datetime, timezone

import polars as pl
import pytest

from analytics.advanced import (
    compute_avg_days_to_first_payment,
    compute_churn_rate,
    compute_ltv,
    compute_retention,
    roi_stats,
)
from enums import PayStatus

pytestmark = pytest.mark.unit


def _dt(y, m, d):
    return datetime(y, m, d, tzinfo=timezone.utc)


# ─────────────────────────────────────────────────────────────────────────────
# compute_ltv
# ─────────────────────────────────────────────────────────────────────────────

def test_ltv_sums_only_paid_payments():
    df = pl.DataFrame(
        {
            "account_id": [1, 1, 2, 2],
            "amount": [100.0, 50.0, 200.0, 999.0],
            "status": [PayStatus.PAID, PayStatus.PAID, PayStatus.PAID, PayStatus.FAILED],
        }
    )
    result = compute_ltv(df)
    d = dict(zip(result["account_id"].to_list(), result["ltv"].to_list()))
    assert d[1] == 150.0
    assert d[2] == 200.0  # failed payment excluded


def test_ltv_empty_when_no_payments():
    df = pl.DataFrame({"account_id": [], "amount": [], "status": []})
    result = compute_ltv(df)
    assert result.is_empty()


def test_ltv_sorted_descending():
    df = pl.DataFrame(
        {
            "account_id": [1, 2, 3],
            "amount": [10.0, 100.0, 50.0],
            "status": [PayStatus.PAID] * 3,
        }
    )
    result = compute_ltv(df)
    assert result["account_id"].to_list() == [2, 3, 1]


# ─────────────────────────────────────────────────────────────────────────────
# compute_churn_rate
# ─────────────────────────────────────────────────────────────────────────────

def test_churn_rate_no_accounts():
    accounts = pl.DataFrame({"account_id": []})
    activity = pl.DataFrame({"account_id": [], "activity_at": []})
    res = compute_churn_rate(accounts, activity, now=_dt(2024, 6, 1), inactive_days=30)
    assert res["churn_rate"] == 0.0
    assert res["total_accounts"] == 0
    assert res["churned_accounts"] == 0
    assert res["inactive_days"] == 30


def test_churn_rate_all_churned_without_activity():
    accounts = pl.DataFrame({"account_id": [1, 2]})
    activity = pl.DataFrame({"account_id": [], "activity_at": []})
    res = compute_churn_rate(accounts, activity, now=_dt(2024, 6, 1), inactive_days=30)
    assert res["churn_rate"] == 1.0
    assert res["churned_accounts"] == 2


def test_churn_rate_recent_activity_not_churned():
    accounts = pl.DataFrame({"account_id": [1, 2]})
    activity = pl.DataFrame(
        {"account_id": [1], "activity_at": [_dt(2024, 5, 25)]}  # 7 days before "now"
    )
    res = compute_churn_rate(accounts, activity, now=_dt(2024, 6, 1), inactive_days=30)
    assert res["total_accounts"] == 2
    assert res["churned_accounts"] == 1  # account 2 has no activity at all
    assert res["churn_rate"] == 0.5


def test_churn_rate_old_activity_counts_as_churned():
    accounts = pl.DataFrame({"account_id": [1]})
    activity = pl.DataFrame({"account_id": [1], "activity_at": [_dt(2024, 1, 1)]})
    res = compute_churn_rate(accounts, activity, now=_dt(2024, 6, 1), inactive_days=30)
    assert res["churn_rate"] == 1.0


# ─────────────────────────────────────────────────────────────────────────────
# compute_avg_days_to_first_payment
# ─────────────────────────────────────────────────────────────────────────────

def test_avg_days_to_first_payment():
    accounts = pl.DataFrame({"account_id": [1, 2], "created_at": [_dt(2024, 1, 1), _dt(2024, 1, 1)]})
    payments = pl.DataFrame(
        {
            "account_id": [1, 1, 2],
            "amount": [10.0, 20.0, 30.0],
            "status": [PayStatus.PAID, PayStatus.PAID, PayStatus.PAID],
            "created_at": [_dt(2024, 1, 5), _dt(2024, 1, 10), _dt(2024, 1, 3)],
        }
    )
    # account 1: first paid = Jan 5 → 4 days; account 2: first paid = Jan 3 → 2 days.
    avg = compute_avg_days_to_first_payment(accounts, payments)
    assert avg == pytest.approx(3.0)


def test_avg_days_to_first_payment_none_when_no_paid():
    accounts = pl.DataFrame({"account_id": [1], "created_at": [_dt(2024, 1, 1)]})
    payments = pl.DataFrame(
        {"account_id": [1], "amount": [10.0], "status": [PayStatus.FAILED], "created_at": [_dt(2024, 1, 2)]}
    )
    assert compute_avg_days_to_first_payment(accounts, payments) is None


# ─────────────────────────────────────────────────────────────────────────────
# compute_retention
# ─────────────────────────────────────────────────────────────────────────────

def test_retention_cohort_size_and_period_zero():
    accounts = pl.DataFrame({"account_id": [1, 2], "created_at": [_dt(2024, 1, 1), _dt(2024, 1, 2)]})
    activity = pl.DataFrame(
        {"account_id": [1, 2], "activity_at": [_dt(2024, 1, 1), _dt(2024, 1, 2)]}
    )
    df = compute_retention(accounts, activity, unit="week", periods=2)
    assert df["cohort_size"].to_list() == [2]
    assert df["period_0"].to_list() == [1.0]  # both active in their own registration week


def test_retention_empty_accounts():
    accounts = pl.DataFrame({"account_id": [], "created_at": []})
    activity = pl.DataFrame({"account_id": [], "activity_at": []})
    df = compute_retention(accounts, activity)
    assert df.is_empty()


# ─────────────────────────────────────────────────────────────────────────────
# roi_stats
# ─────────────────────────────────────────────────────────────────────────────

def test_roi_stats_unavailable_stub():
    res = roi_stats()
    assert res["available"] is False
    assert "CAC" in res["reason"]
