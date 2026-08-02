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
    Курсы забираются у готового провайдера (`billing.fx.provider`) — ЦБ РФ,
    Frankfurter, ExchangeRate-API и т.п.; формат ответа каждого известен
    заранее, см. `services/fx_providers.py`. Тем, кому нужен ключ, он
    берётся из `billing.fx.api_key`. Отдельный вариант `provider=lua` —
    курсы отдаёт Lua-скрипт, это способ подключить источник, которого нет в
    списке. Ручные курсы из `billing.fx.rates` имеют приоритет: ими можно
    перекрыть отдельную валюту, не отключая провайдера.

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
from services.fx_providers import (
    FxProviderError,
    QUOTE_BASE_PER_UNIT,
    QUOTE_UNIT_PER_BASE,
    by_key,
    fetch_rates,
)
from utils.degrade import VALKEY_ERRORS

log = logging.getLogger("saviorbill.fx")

_CENT = Decimal("0.01")
_HUNDRED = Decimal("100")

DEFAULT_CURRENCY = "RUB"
DEFAULT_SOURCE = "manual"
DEFAULT_CACHE_TTL = 900
_CACHE_KEY = "fx:rates"
_HTTP_TIMEOUT = 10.0


class FxError(Exception):
    """Курс недоступен — зачислять нельзя."""


class FxRates:
    """Чтение курсов и конвертация сумм в базовую валюту."""

    def __init__(
        self,
        settings: SystemSettingsMngr,
        vk: valkey.Valkey,
        bus=None,  # noqa: ANN001 — LuaBus | None, для источника "lua"
        session=None,  # noqa: ANN001 — AsyncSession | None, для источника "lua"
    ) -> None:
        self.settings = settings
        self.vk = vk
        self.bus = bus
        self.session = session

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
        """Курсы от выбранного провайдера (`billing.fx.provider`) с кэшем."""
        cached = await self._cached()
        if cached is not None:
            return cached

        base = await self.base_currency()
        provider_key = (await self.settings.get("billing.fx.provider")) or ""
        api_key = (await self.settings.get("billing.fx.api_key")) or ""

        if provider_key == "lua":
            rates = await self._lua_rates()
        else:
            provider = by_key(provider_key)
            if provider is None:
                raise FxError(
                    f"fx: неизвестный провайдер курсов {provider_key!r} "
                    "(см. billing.fx.provider)"
                )
            rates = await fetch_rates(provider, base, api_key)

        await self._cache(rates)
        return rates

    async def _lua_rates(self) -> dict[str, Decimal]:
        """Курсы из Lua-скрипта (`billing.fx.lua_slug`).

        Скрипт должен вернуть ``{ public = { rates = { USD = "95.5", … } } }``
        — «сколько базовой валюты за одну единицу указанной». Так подключается
        любой источник, которого нет в списке готовых провайдеров.
        """
        if self.bus is None or self.session is None:
            raise FxError("fx: источник 'lua' недоступен без шины LuaWorker")

        from lua.context import LuaRunner
        from models.system_scripts import SystemScriptsModel, resolve_version_filename
        from sqlalchemy import select

        slug = (await self.settings.get("billing.fx.lua_slug")) or ""
        if not slug:
            raise FxError("fx: не выбран Lua-скрипт (billing.fx.lua_slug)")
        script = await self.session.scalar(
            select(SystemScriptsModel).where(SystemScriptsModel.slug == slug)
        )
        if script is None or not script.is_active:
            raise FxError(f"fx: Lua-скрипт {slug!r} не найден или выключен")

        filename = await resolve_version_filename(self.session, script, None)
        res = await LuaRunner(self.bus).run(
            filename, script.kind, {"action": "rates"}, slug=script.slug
        )
        node = (res.get("public") or {}).get("rates")
        if not isinstance(node, dict):
            raise FxError(f"fx: скрипт {slug!r} не вернул public.rates")

        out: dict[str, Decimal] = {}
        for code, value in node.items():
            try:
                rate = Decimal(str(value))
            except (ArithmeticError, ValueError):
                continue
            if rate > 0:
                out[str(code).strip().upper()] = rate
        if not out:
            raise FxError(f"fx: скрипт {slug!r} вернул пустой список курсов")
        return out

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
            except FxProviderError as exc:
                raise FxError(str(exc)) from exc
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
