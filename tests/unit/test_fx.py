"""Конвертация зачислений в базовую валюту инстанса (AUDIT.md §2.3)."""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from services.fx import FxError, FxRates, QUOTE_UNIT_PER_BASE

pytestmark = pytest.mark.unit


class _Settings:
    def __init__(self, **values) -> None:
        self.values = values

    async def get(self, key, default=None):
        return self.values.get(key, default)

    async def get_int(self, key, default=None):
        raw = self.values.get(key)
        return int(raw) if raw is not None else default


class _Valkey:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, ex=None):
        self.store[key] = value


def _fx(**settings):
    return FxRates(_Settings(**settings), _Valkey())


@pytest.mark.asyncio
async def test_base_currency_defaults_to_rub():
    assert await _fx().base_currency() == "RUB"


@pytest.mark.asyncio
async def test_same_currency_is_not_converted():
    fx = _fx(**{"billing.currency": "RUB"})
    amount, rate, base = await fx.to_base(Decimal("100.00"), "RUB")
    assert (amount, rate, base) == (Decimal("100.00"), Decimal(1), "RUB")


@pytest.mark.asyncio
async def test_manual_rate_is_applied():
    fx = _fx(
        **{
            "billing.currency": "RUB",
            "billing.fx.rates": json.dumps({"USD": "95.5"}),
        }
    )
    amount, rate, base = await fx.to_base(Decimal("10.00"), "usd")
    assert amount == Decimal("955.00")
    assert rate == Decimal("95.5")
    assert base == "RUB"


@pytest.mark.asyncio
async def test_markup_reduces_credited_amount():
    fx = _fx(
        **{
            "billing.fx.rates": json.dumps({"USD": "100"}),
            "billing.fx.markup_percent": 2,
        }
    )
    amount, _, _ = await fx.to_base(Decimal("10.00"), "USD")
    assert amount == Decimal("980.00")


@pytest.mark.asyncio
async def test_markup_never_applies_to_the_base_currency():
    fx = _fx(**{"billing.fx.markup_percent": 10})
    amount, _, _ = await fx.to_base(Decimal("10.00"), "RUB")
    assert amount == Decimal("10.00")


@pytest.mark.asyncio
async def test_unknown_currency_raises_instead_of_crediting_as_is():
    fx = _fx(**{"billing.fx.rates": json.dumps({"USD": "95.5"})})
    with pytest.raises(FxError):
        await fx.to_base(Decimal("10.00"), "EUR")


@pytest.mark.asyncio
async def test_broken_rates_json_is_ignored_not_fatal():
    fx = _fx(**{"billing.fx.rates": "{not json"})
    with pytest.raises(FxError):
        await fx.to_base(Decimal("1"), "USD")


@pytest.mark.asyncio
async def test_api_rates_are_read_by_path_and_cached(monkeypatch):
    calls = {"n": 0}

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            calls["n"] += 1
            return {"data": {"rates": {"USD": "90"}}}

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_a):
            return False

        async def get(self, _url):
            return _Resp()

    monkeypatch.setattr("services.fx.httpx.AsyncClient", lambda **_kw: _Client())
    fx = _fx(
        **{
            "billing.fx.source": "api",
            "billing.fx.api_url": "https://rates.example/api",
            "billing.fx.api_path": "data.rates",
        }
    )
    amount, rate, _ = await fx.to_base(Decimal("2"), "USD")
    assert amount == Decimal("180.00") and rate == Decimal("90")

    # Второй вызов берёт курсы из кэша, а не ходит в API снова.
    await fx.to_base(Decimal("1"), "USD")
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_inverse_quote_is_normalised(monkeypatch):
    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"USD": "0.01"}  # 1 RUB = 0.01 USD

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_a):
            return False

        async def get(self, _url):
            return _Resp()

    monkeypatch.setattr("services.fx.httpx.AsyncClient", lambda **_kw: _Client())
    fx = _fx(
        **{
            "billing.fx.source": "api",
            "billing.fx.api_url": "https://rates.example/api",
            "billing.fx.api_quote": QUOTE_UNIT_PER_BASE,
        }
    )
    amount, _, _ = await fx.to_base(Decimal("1"), "USD")
    assert amount == Decimal("100.00")


@pytest.mark.asyncio
async def test_manual_rate_overrides_api(monkeypatch):
    def _boom(**_kw):
        raise AssertionError("API не должен вызываться при ручном курсе")

    monkeypatch.setattr("services.fx.httpx.AsyncClient", _boom)
    fx = _fx(
        **{
            "billing.fx.source": "api",
            "billing.fx.api_url": "https://rates.example/api",
            "billing.fx.rates": json.dumps({"USD": "99"}),
        }
    )
    _, rate, _ = await fx.to_base(Decimal("1"), "USD")
    assert rate == Decimal("99")
