"""Курсы валют и конвертация зачислений в базовую валюту инстанса.

`payments.currency` есть у каждого платежа, а у `accounts.balance` валюты нет:
до этого модуля платёж в USD молча прибавлялся к рублёвому балансу как есть
(см. AUDIT.md §2.3). Теперь зачисление приводится к базовой валюте
(`billing.currency`, по умолчанию RUB).

Источник курсов — настройка `billing.fx.source`:

``manual``
    Курсы задаются вручную в `billing.fx.rates` — JSON вида
    ``{"USD": "95.5", "USDT": "95.0"}``: сколько базовой валюты стоит одна
    единица указанной.

``api``
    Курсы забираются с внешнего JSON-API (`billing.fx.api_url`). Формат ответа
    у сервисов разный, поэтому путь до объекта с курсами задаётся отдельно
    (`billing.fx.api_path`, например ``data.rates``), а направление котировки —
    флагом `billing.fx.api_quote`. Ручные курсы из `billing.fx.rates` при этом
    имеют приоритет: ими можно перекрыть отдельную валюту, не отключая API.

Неизвестная валюта — это ошибка, а не повод зачислить сумму «как есть»:
конвертация бросает исключение, вебхук отвечает 5xx, провайдер повторит
доставку, а оператор успеет задать курс.
"""

from __future__ import annotations

import json
import logging
from decimal import Decimal, ROUND_HALF_UP

import httpx
import valkey.asyncio as valkey

from models.system_settings import SystemSettingsMngr
from utils.degrade import VALKEY_ERRORS

log = logging.getLogger("saviorbill.fx")

_CENT = Decimal("0.01")
_HUNDRED = Decimal("100")

DEFAULT_CURRENCY = "RUB"
DEFAULT_SOURCE = "manual"
DEFAULT_CACHE_TTL = 900
_CACHE_KEY = "fx:rates"
_HTTP_TIMEOUT = 10.0

#: Курс в ответе API — «сколько базовой валюты за одну единицу иностранной».
QUOTE_BASE_PER_UNIT = "base_per_unit"
#: Обратная котировка — «сколько иностранной валюты за одну единицу базовой».
QUOTE_UNIT_PER_BASE = "unit_per_base"


class FxError(Exception):
    """Курс недоступен — зачислять нельзя."""


def _dig(data: dict, path: str):
    """Достать вложенное значение по точечному пути (пустой путь — корень)."""
    node = data
    for part in filter(None, path.split(".")):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


class FxRates:
    """Чтение курсов и конвертация сумм в базовую валюту."""

    def __init__(self, settings: SystemSettingsMngr, vk: valkey.Valkey) -> None:
        self.settings = settings
        self.vk = vk

    async def base_currency(self) -> str:
        value = await self.settings.get("billing.currency")
        return (value or DEFAULT_CURRENCY).strip().upper()

    async def _manual_rates(self) -> dict[str, Decimal]:
        raw = await self.settings.get("billing.fx.rates")
        if not raw:
            return {}
        try:
            data = json.loads(raw)
        except ValueError:
            log.warning("billing.fx.rates is not valid JSON, ignoring")
            return {}
        out: dict[str, Decimal] = {}
        for code, value in (data or {}).items():
            try:
                rate = Decimal(str(value))
            except ArithmeticError:
                log.warning("billing.fx.rates: bad rate for %s: %r", code, value)
                continue
            if rate > 0:
                out[str(code).strip().upper()] = rate
        return out

    async def _api_rates(self) -> dict[str, Decimal]:
        url = await self.settings.get("billing.fx.api_url")
        if not url:
            return {}
        cached = await self._cached()
        if cached is not None:
            return cached

        path = (await self.settings.get("billing.fx.api_path")) or ""
        quote = (
            await self.settings.get("billing.fx.api_quote")
        ) or QUOTE_BASE_PER_UNIT
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            payload = resp.json()

        node = _dig(payload if isinstance(payload, dict) else {}, path)
        if not isinstance(node, dict):
            raise FxError(f"fx api: no rates object at path {path!r}")

        rates: dict[str, Decimal] = {}
        for code, value in node.items():
            try:
                rate = Decimal(str(value))
            except ArithmeticError:
                continue
            if rate <= 0:
                continue
            code = str(code).strip().upper()
            rates[code] = (Decimal(1) / rate) if quote == QUOTE_UNIT_PER_BASE else rate

        await self._cache(rates)
        return rates

    async def _cached(self) -> dict[str, Decimal] | None:
        try:
            raw = await self.vk.get(_CACHE_KEY)
        except VALKEY_ERRORS:
            return None
        if not raw:
            return None
        try:
            return {k: Decimal(v) for k, v in json.loads(raw).items()}
        except (ValueError, ArithmeticError):
            return None

    async def _cache(self, rates: dict[str, Decimal]) -> None:
        ttl = await self.settings.get_int("billing.fx.cache_ttl_sec", DEFAULT_CACHE_TTL)
        try:
            await self.vk.set(
                _CACHE_KEY,
                json.dumps({k: str(v) for k, v in rates.items()}),
                ex=ttl or DEFAULT_CACHE_TTL,
            )
        except VALKEY_ERRORS:
            log.warning("fx: rates could not be cached, valkey unavailable")

    async def rate_to_base(self, currency: str) -> Decimal:
        """Сколько базовой валюты стоит одна единица ``currency``."""
        currency = (currency or "").strip().upper()
        base = await self.base_currency()
        if not currency or currency == base:
            return Decimal(1)

        manual = await self._manual_rates()
        if currency in manual:
            return manual[currency]

        source = (await self.settings.get("billing.fx.source")) or DEFAULT_SOURCE
        if source == "api":
            try:
                api = await self._api_rates()
            except (httpx.HTTPError, ValueError) as exc:
                raise FxError(f"fx api unavailable: {exc}") from exc
            if currency in api:
                return api[currency]

        raise FxError(f"no exchange rate for {currency} -> {base}")

    async def to_base(self, amount: Decimal, currency: str) -> tuple[Decimal, Decimal, str]:
        """Привести сумму к базовой валюте.

        :return: ``(сумма в базовой валюте, применённый курс, базовая валюта)``.
        """
        base = await self.base_currency()
        rate = await self.rate_to_base(currency)
        converted = amount * rate
        if rate != 1:
            markup = await self.settings.get_int("billing.fx.markup_percent", 0) or 0
            if markup:
                converted -= converted * Decimal(markup) / _HUNDRED
        return converted.quantize(_CENT, rounding=ROUND_HALF_UP), rate, base


__all__ = [
    "DEFAULT_CURRENCY",
    "FxError",
    "FxRates",
    "QUOTE_BASE_PER_UNIT",
    "QUOTE_UNIT_PER_BASE",
]
