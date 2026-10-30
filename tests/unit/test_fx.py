"""Конвертация зачислений в базовую валюту инстанса (AUDIT.md §2.3)."""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from services.fx import FxError, FxRates
from services.fx_providers import FxProviderError, by_key, fetch_rates

pytestmark = pytest.mark.unit


class _Settings:
    def __init__(self, **values) -> None:
        self.values = values

    async def get(self, key, default=None):
        return self.values.get(key, default)

    async def get_int(self, key, default=None):
        raw = self.values.get(key)
        return int(raw) if raw is not None else default

    async def get_bool(self, key, default=False):
        raw = self.values.get(key)
        return str(raw).lower() in ("1", "true", "yes") if raw is not None else default


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
async def test_provider_rates_are_parsed_and_cached(monkeypatch):
    """Курсы провайдера разбираются по его формату и кладутся в кэш."""
    calls = {"n": 0}

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            calls["n"] += 1
            # open.er-api.com отдаёт "сколько валюты за 1 базовую".
            return {"rates": {"USD": "0.0111111111"}}

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_a):
            return False

        async def get(self, _url):
            return _Resp()

    monkeypatch.setattr("services.fx_providers.httpx.AsyncClient", lambda **_kw: _Client())
    fx = _fx(
        **{
            "billing.fx.source": "api",
            "billing.fx.provider": "erapi",
        }
    )
    _, rate, _ = await fx.to_base(Decimal("1"), "USD")
    assert rate.quantize(Decimal("1")) == Decimal("90")

    # Второй вызов берёт курсы из кэша, а не ходит в сеть снова.
    await fx.to_base(Decimal("1"), "USD")
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_cbr_parses_nominal(monkeypatch):
    """У ЦБ курс указан за Nominal единиц — делим, иначе завышаем в разы."""

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "Valute": {
                    "JPY": {"CharCode": "JPY", "Nominal": 100, "Value": 62.5},
                    "USD": {"CharCode": "USD", "Nominal": 1, "Value": 90.0},
                }
            }

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_a):
            return False

        async def get(self, _url):
            return _Resp()

    monkeypatch.setattr("services.fx_providers.httpx.AsyncClient", lambda **_kw: _Client())
    rates = await fetch_rates(by_key("cbr"), "RUB", "")
    assert rates["USD"] == Decimal("90.0")
    assert rates["JPY"] == Decimal("0.625")


@pytest.mark.asyncio
async def test_provider_needing_key_fails_without_one():
    with pytest.raises(FxProviderError, match="ключ"):
        await fetch_rates(by_key("exchangerate_api"), "RUB", "")


@pytest.mark.asyncio
async def test_cbr_rejects_non_rub_base():
    with pytest.raises(FxProviderError, match="RUB"):
        await fetch_rates(by_key("cbr"), "USD", "")


@pytest.mark.asyncio
async def test_unknown_provider_is_an_error():
    fx = _fx(**{"billing.fx.source": "api", "billing.fx.provider": "nope"})
    with pytest.raises(FxError, match="неизвестный провайдер"):
        await fx.to_base(Decimal("1"), "USD")


@pytest.mark.asyncio
async def test_manual_rate_overrides_provider(monkeypatch):
    def _boom(**_kw):
        raise AssertionError("провайдер не должен вызываться при ручном курсе")

    monkeypatch.setattr("services.fx_providers.httpx.AsyncClient", _boom)
    fx = _fx(
        **{
            "billing.fx.source": "api",
            "billing.fx.provider": "erapi",
            "billing.fx.rates": json.dumps({"USD": "99"}),
        }
    )
    _, rate, _ = await fx.to_base(Decimal("1"), "USD")
    assert rate == Decimal("99")


@pytest.mark.asyncio
async def test_multi_source_priority_order():
    """Источники опрашиваются строго по порядку в billing.fx.sources."""
    sources = [
        {"id": "src_top", "type": "manual", "enabled": True},
        {"id": "src_bottom", "type": "manual", "enabled": True},
    ]
    fx = _fx(
        **{
            "billing.currency": "RUB",
            "billing.fx.sources": json.dumps(sources),
            "billing.fx.rates": json.dumps({"USD": "91.0", "EUR": "100.0"}),
        }
    )
    rate = await fx.rate_to_base("USD")
    assert rate == Decimal("91.0")


@pytest.mark.asyncio
async def test_from_base_conversion():
    """from_base конвертирует сумму из базовой валюты инстанса в целевую."""
    fx = _fx(
        **{
            "billing.currency": "USD",
            "billing.fx.rates": json.dumps({"RUB": "0.01"}),
        }
    )
    target_amount, rate = await fx.from_base(Decimal("10.00"), "RUB")
    assert rate == Decimal("0.01")
    assert target_amount == Decimal("1000.00")


@pytest.mark.asyncio
async def test_from_base_with_markup():
    """Спред увеличивает сумму к оплате в целевой валюте."""
    fx = _fx(
        **{
            "billing.currency": "USD",
            "billing.fx.rates": json.dumps({"RUB": "0.01"}),
            "billing.fx.markup_percent": 5,
        }
    )
    target_amount, _ = await fx.from_base(Decimal("10.00"), "RUB")
    assert target_amount == Decimal("1050.00")


@pytest.mark.asyncio
async def test_to_base_with_locked_rate():
    """При передаче locked_rate конвертация использует его напрямую без обращения к live-курсам."""
    fx = _fx(
        **{
            "billing.currency": "USD",
            "billing.fx.rates": json.dumps({"RUB": "0.02"}),
        }
    )
    base_amount, rate, base = await fx.to_base(
        Decimal("950.00"), "RUB", locked_rate=Decimal("0.01")
    )
    assert rate == Decimal("0.01")
    assert base == "USD"
    assert base_amount == Decimal("9.50")


@pytest.mark.asyncio
async def test_fail_open_uses_last_rates():
    """Если источник падает, но включен fail_open и есть last_rates, возвращаются сохранённые курсы."""
    sources = [
        {
            "id": "src_broken",
            "type": "provider",
            "provider": "nope",
            "enabled": True,
            "last_rates": {"USD": "95.5"},
        }
    ]
    fx = _fx(
        **{
            "billing.currency": "RUB",
            "billing.fx.sources": json.dumps(sources),
            "billing.fx.fail_open": "true",
        }
    )
    _, rate, _ = await fx.to_base(Decimal("1"), "USD")
    assert rate == Decimal("95.5")
