"""Источники курсов валют: готовые провайдеры вместо универсального конфига.

Раньше `billing.fx.source=api` требовал вручную описать чужой JSON: URL, путь
до объекта с курсами и направление котировки. На практике это всегда одни и те
же несколько сервисов с фиксированным форматом, зато у половины из них нужен
API-ключ, который в такую схему вообще не вписывался.

Здесь каждый провайдер описан кодом: как построить URL (включая ключ) и как
разобрать ответ. Админ выбирает провайдера из списка и, если нужно, вводит
ключ — остальное известно заранее.

Отдельный вариант — ``lua``: курсы отдаёт Lua-скрипт (`billing.fx.lua_slug`).
Он должен вернуть ``{ public = { rates = { USD = "95.5", ... } } }`` — так
подключается любой источник, которого здесь нет, включая приватные и те, что
требуют нестандартной авторизации.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Callable

import httpx

log = logging.getLogger("saviorbill.fx.providers")

_HTTP_TIMEOUT = 10.0

#: Курс — «сколько базовой валюты за одну единицу иностранной».
QUOTE_BASE_PER_UNIT = "base_per_unit"
#: Обратная котировка — «сколько иностранной за одну единицу базовой».
QUOTE_UNIT_PER_BASE = "unit_per_base"


class FxProviderError(Exception):
    """Провайдер не отдал курсы (сеть, ключ, формат ответа)."""


@dataclass(frozen=True, slots=True)
class FxProvider:
    """Описание источника курсов."""

    key: str
    title: str
    #: Нужен ли API-ключ (`billing.fx.api_key`).
    needs_key: bool
    #: Где взять ключ — показывается в подсказке админки.
    signup_url: str | None
    #: Строит URL запроса: (base, api_key) -> url.
    build_url: Callable[[str, str], str]
    #: Разбирает ответ в {код валюты: сколько базовой за единицу}.
    parse: Callable[[dict, str], dict[str, Decimal]]
    #: Работает только с этой базовой валютой (None — с любой).
    fixed_base: str | None = None
    note: str = ""


def _to_decimal(value: object) -> Decimal | None:
    try:
        rate = Decimal(str(value))
    except (ArithmeticError, ValueError):
        return None
    return rate if rate > 0 else None


def _invert(rates: dict[str, Decimal]) -> dict[str, Decimal]:
    """Перевернуть котировку unit_per_base -> base_per_unit."""
    return {code: (Decimal(1) / rate) for code, rate in rates.items() if rate > 0}


def _parse_cbr(payload: dict, _base: str) -> dict[str, Decimal]:
    """ЦБ РФ: `Valute: {USD: {CharCode, Nominal, Value}}`, всё в рублях."""
    valute = payload.get("Valute")
    if not isinstance(valute, dict):
        raise FxProviderError("ЦБ РФ: в ответе нет объекта Valute")
    out: dict[str, Decimal] = {}
    for item in valute.values():
        if not isinstance(item, dict):
            continue
        code = str(item.get("CharCode") or "").strip().upper()
        value = _to_decimal(item.get("Value"))
        nominal = _to_decimal(item.get("Nominal")) or Decimal(1)
        if code and value:
            out[code] = value / nominal
    return out


def _parse_flat_unit_per_base(key: str) -> Callable[[dict, str], dict[str, Decimal]]:
    """Парсер для сервисов, отдающих «сколько иностранной за 1 базовую»."""

    def parse(payload: dict, _base: str) -> dict[str, Decimal]:
        node = payload.get(key)
        if not isinstance(node, dict):
            raise FxProviderError(f"в ответе нет объекта {key!r}")
        rates = {
            str(code).strip().upper(): rate
            for code, raw in node.items()
            if (rate := _to_decimal(raw)) is not None
        }
        return _invert(rates)

    return parse


def _parse_openexchangerates(payload: dict, base: str) -> dict[str, Decimal]:
    """OpenExchangeRates: на бесплатном тарифе база всегда USD."""
    node = payload.get("rates")
    if not isinstance(node, dict):
        raise FxProviderError("OpenExchangeRates: в ответе нет объекта rates")
    per_usd = {
        str(code).strip().upper(): rate
        for code, raw in node.items()
        if (rate := _to_decimal(raw)) is not None
    }
    # Ответ — «сколько валюты за 1 USD». Нужна база инстанса: пересчитываем
    # через курс базовой валюты к доллару.
    if base == "USD":
        return _invert(per_usd)
    base_per_usd = per_usd.get(base)
    if not base_per_usd:
        raise FxProviderError(
            f"OpenExchangeRates: в ответе нет курса базовой валюты {base}"
        )
    return {code: (base_per_usd / rate) for code, rate in per_usd.items() if rate > 0}


PROVIDERS: tuple[FxProvider, ...] = (
    FxProvider(
        key="cbr",
        title="ЦБ РФ",
        needs_key=False,
        signup_url=None,
        fixed_base="RUB",
        build_url=lambda _base, _key: "https://www.cbr-xml-daily.ru/daily_json.js",
        parse=_parse_cbr,
        note="Официальные курсы ЦБ, обновляются раз в сутки. Только для базовой валюты RUB.",
    ),
    FxProvider(
        key="frankfurter",
        title="Frankfurter (ЕЦБ)",
        needs_key=False,
        signup_url=None,
        build_url=lambda base, _key: f"https://api.frankfurter.dev/v1/latest?base={base}",
        parse=_parse_flat_unit_per_base("rates"),
        note="Данные ЕЦБ, без ключа и лимитов. Только валюты ЕЦБ — RUB там нет, для рублёвой базы не подойдёт.",
    ),
    FxProvider(
        key="erapi",
        title="open.er-api.com",
        needs_key=False,
        signup_url=None,
        build_url=lambda base, _key: f"https://open.er-api.com/v6/latest/{base}",
        parse=_parse_flat_unit_per_base("rates"),
        note="Бесплатно и без ключа, обновление раз в сутки.",
    ),
    FxProvider(
        key="exchangerate_api",
        title="ExchangeRate-API",
        needs_key=True,
        signup_url="https://www.exchangerate-api.com/",
        build_url=lambda base, key: f"https://v6.exchangerate-api.com/v6/{key}/latest/{base}",
        parse=_parse_flat_unit_per_base("conversion_rates"),
        note="Требует ключ. На бесплатном тарифе обновление раз в сутки.",
    ),
    FxProvider(
        key="openexchangerates",
        title="OpenExchangeRates",
        needs_key=True,
        signup_url="https://openexchangerates.org/",
        build_url=lambda _base, key: f"https://openexchangerates.org/api/latest.json?app_id={key}",
        parse=_parse_openexchangerates,
        note="Требует ключ. На бесплатном тарифе база фиксирована (USD) — пересчёт делаем сами.",
    ),
)

_BY_KEY = {p.key: p for p in PROVIDERS}


def by_key(key: str) -> FxProvider | None:
    return _BY_KEY.get((key or "").strip())


async def fetch_rates(provider: FxProvider, base: str, api_key: str) -> dict[str, Decimal]:
    """Забрать и разобрать курсы у провайдера.

    :raises FxProviderError: сеть/HTTP-ошибка, отсутствующий ключ либо
        неожиданный формат ответа.
    """
    if provider.needs_key and not api_key:
        raise FxProviderError(f"{provider.title}: не задан API-ключ")
    if provider.fixed_base and provider.fixed_base != base:
        raise FxProviderError(
            f"{provider.title}: работает только с базовой валютой "
            f"{provider.fixed_base}, а у инстанса {base}"
        )

    url = provider.build_url(base, api_key)
    try:
        # follow_redirects — сервисы курсов периодически переезжают на новый
        # домен и отвечают 301 (так случилось с api.frankfurter.app); без
        # этого источник просто переставал работать без внятной причины.
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            payload = resp.json()
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code
        if code in (401, 403):
            hint = " — вероятно, неверный или просроченный API-ключ"
        elif code == 404:
            hint = (
                f" — источник не знает базовую валюту {base}"
                " (проверьте, что он её котирует)"
            )
        elif code == 429:
            hint = " — превышен лимит запросов, увеличьте TTL кэша курсов"
        else:
            hint = ""
        raise FxProviderError(f"{provider.title}: HTTP {code}{hint}") from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise FxProviderError(f"{provider.title}: {exc}") from exc

    if not isinstance(payload, dict):
        raise FxProviderError(f"{provider.title}: ответ не является JSON-объектом")

    rates = provider.parse(payload, base)
    rates.pop(base, None)  # курс базовой к самой себе не нужен
    if not rates:
        raise FxProviderError(f"{provider.title}: в ответе не нашлось ни одного курса")
    return rates


__all__ = [
    "PROVIDERS",
    "FxProvider",
    "FxProviderError",
    "QUOTE_BASE_PER_UNIT",
    "QUOTE_UNIT_PER_BASE",
    "by_key",
    "fetch_rates",
]
