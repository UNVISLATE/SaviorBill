"""Курсы валют и конвертация зачислений в базовую валюту инстанса.

`payments.currency` есть у каждого платежа, а у `accounts.balance` валюты нет:
платёж приводится к базовой валюте (`billing.currency`, по умолчанию RUB).

Источники курсов хранятся в БД (таблица `fx_sources`) и опрашиваются строго по
приоритету (0..N). При успешном получении курсы кэшируются в Valkey и сохраняются
в БД (`last_rates`). При ошибке источника:
- Если включён режим Fail-Open (`billing.fx.fail_open`), биллинг использует
  последние сохранённые курсы из БД, фиксируя ошибку (`last_error`);
- Если Fail-Open выключен, опрашивается следующий источник по цепочке.
"""

from __future__ import annotations

import json
import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

import httpx
import valkey.asyncio as valkey
from sqlalchemy import select

from models.system_settings import SystemSettingsMngr
from services.fx_providers import (
    FxProviderError,
    QUOTE_BASE_PER_UNIT,
    QUOTE_UNIT_PER_BASE,
    by_key,
    fetch_rates,
)
from utils.datetime_utils import utc_now
from utils.degrade import VALKEY_ERRORS

log = logging.getLogger("saviorbill.fx")

_CENT = Decimal("0.01")
_HUNDRED = Decimal("100")

DEFAULT_CURRENCY = "RUB"
DEFAULT_SOURCE = "manual"
DEFAULT_CACHE_TTL = 900
_CACHE_KEY_PREFIX = "fx:rates:src:"
_HTTP_TIMEOUT = 10.0


class FxError(Exception):
    """Курс недоступен — операция отклоняется."""


class FxRates:
    """Чтение курсов с цепочкой приоритетов и двусторонняя конвертация."""

    def __init__(
        self,
        settings: SystemSettingsMngr,
        vk: valkey.Valkey,
        bus=None,  # noqa: ANN001 — LuaBus | None
        session=None,  # noqa: ANN001 — AsyncSession | None
        box=None,  # noqa: ANN001 — SecBox | None
    ) -> None:
        self.settings = settings
        self.vk = vk
        self.bus = bus
        self.session = session
        self.box = box

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

    async def get_sources(self) -> list[Any]:
        """Получить упорядоченный список источников курсов с приоритетами (0..N).

        Сначала читает из таблицы `fx_sources` в БД. Если сессии нет или таблица
        пуста, обращается к `billing.fx.sources` или устаревшим настройкам.
        """
        if self.session is not None:
            try:
                from models.fx_sources import FxSourcesModel

                stmt = select(FxSourcesModel).order_by(
                    FxSourcesModel.priority.asc(), FxSourcesModel.id.asc()
                )
                rows = list(await self.session.scalars(stmt))
                if rows:
                    return rows
            except Exception as exc:  # noqa: BLE001
                log.warning("fx: could not load fx_sources from db: %s", exc)

        # Fallback на JSON-настройки (для тестов или первичной миграции)
        raw = await self.settings.get("billing.fx.sources")
        if raw:
            try:
                data = json.loads(raw)
                if isinstance(data, list) and data:
                    return data
            except (ValueError, TypeError):
                log.warning("billing.fx.sources is not valid JSON list")

        source = (await self.settings.get("billing.fx.source")) or DEFAULT_SOURCE
        provider_key = (await self.settings.get("billing.fx.provider")) or ""
        api_key = (await self.settings.get("billing.fx.api_key")) or ""
        lua_slug = (await self.settings.get("billing.fx.lua_slug")) or ""

        if source == "api":
            if provider_key == "lua":
                return [
                    {"id": "manual", "type": "manual", "name": "Ручные курсы", "enabled": True},
                    {"id": "lua", "type": "lua", "lua_slug": lua_slug, "name": "Lua-скрипт", "enabled": True},
                ]
            return [
                {"id": "manual", "type": "manual", "name": "Ручные курсы", "enabled": True},
                {
                    "id": "provider",
                    "type": "provider",
                    "provider": provider_key,
                    "api_key": api_key,
                    "name": provider_key or "Провайдер API",
                    "enabled": True,
                },
            ]

        return [{"id": "manual", "type": "manual", "name": "Ручные курсы", "enabled": True}]

    async def _fetch_provider_rates(self, provider_key: str, api_key: str) -> dict[str, Decimal]:
        base = await self.base_currency()
        provider = by_key(provider_key)
        if provider is None:
            raise FxError(f"fx: неизвестный провайдер курсов {provider_key!r}")
        return await fetch_rates(provider, base, api_key)

    async def _fetch_lua_rates(self, slug: str) -> dict[str, Decimal]:
        if self.bus is None or self.session is None:
            raise FxError("fx: источник 'lua' недоступен без шины LuaWorker")

        from lua.context import LuaRunner
        from models.system_scripts import SystemScriptsModel, resolve_version_filename
        from sqlalchemy import select

        if not slug:
            raise FxError("fx: не выбран Lua-скрипт")
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

    async def _cached_for(self, cache_key: str) -> dict[str, Decimal] | None:
        try:
            raw = await self.vk.get(cache_key)
        except VALKEY_ERRORS:
            return None
        if not raw:
            return None
        try:
            return {k: Decimal(v) for k, v in json.loads(raw).items()}
        except (ValueError, ArithmeticError):
            return None

    async def _cache_for(self, cache_key: str, rates: dict[str, Decimal]) -> None:
        ttl = await self.settings.get_int("billing.fx.cache_ttl_sec", DEFAULT_CACHE_TTL)
        try:
            await self.vk.set(
                cache_key,
                json.dumps({k: str(v) for k, v in rates.items()}),
                ex=ttl or DEFAULT_CACHE_TTL,
            )
        except VALKEY_ERRORS:
            log.warning("fx: rates could not be cached for %s, valkey unavailable", cache_key)

    def _decrypt_key(self, enc_key: str) -> str:
        if not enc_key or not self.box:
            return ""
        try:
            return self.box.open(enc_key) or ""
        except Exception:
            return ""

    async def _rates_for_source(self, src: Any) -> dict[str, Decimal]:
        """Получить курсы от одного источника (Valkey -> Live -> Fail-Open DB)."""
        is_orm = hasattr(src, "type")
        src_type = src.type if is_orm else src.get("type")
        src_id = src.id if is_orm else (src.get("id") or src_type or "default")

        if src_type == "manual":
            raw_rates = getattr(src, "rates", None) if is_orm else src.get("rates")
            out: dict[str, Decimal] = {}
            if raw_rates and isinstance(raw_rates, dict) and len(raw_rates) > 0:
                for k, v in raw_rates.items():
                    try:
                        d = Decimal(str(v))
                        if d > 0:
                            out[str(k).strip().upper()] = d
                    except (ValueError, ArithmeticError):
                        continue
            if not out:
                out = await self._manual_rates()
            if is_orm and self.session is not None:
                src.last_rates = {k: str(v) for k, v in out.items()}
                src.last_fetched_at = utc_now()
                src.last_error = None
                src.last_error_at = None
                await self.session.flush()
            return out

        cache_key = f"{_CACHE_KEY_PREFIX}{src_id}"
        cached = await self._cached_for(cache_key)
        if cached is not None:
            return cached

        # Получаем API-ключ
        api_key = ""
        if is_orm and getattr(src, "api_key_enc", None):
            api_key = self._decrypt_key(src.api_key_enc)
        if not api_key and not is_orm:
            api_key = src.get("api_key") or ""
        if not api_key:
            api_key = (await self.settings.get("billing.fx.api_key")) or ""

        try:
            if src_type == "provider":
                prov_key = src.provider if is_orm else (src.get("provider") or "")
                rates = await self._fetch_provider_rates(prov_key, api_key)
            elif src_type == "lua":
                slug = src.lua_slug if is_orm else (src.get("lua_slug") or "")
                rates = await self._fetch_lua_rates(slug)
            else:
                return {}

            # Успешное получение — сохраняем кэш и статус в БД
            await self._cache_for(cache_key, rates)
            if is_orm and self.session is not None:
                src.last_rates = {k: str(v) for k, v in rates.items()}
                src.last_fetched_at = utc_now()
                src.last_error = None
                src.last_error_at = None
                await self.session.flush()

            return rates

        except Exception as exc:
            log.warning("fx: source %r failed: %s", src_id, exc)

            # Фиксируем ошибку в БД
            if is_orm and self.session is not None:
                src.last_error = str(exc)[:1024]
                src.last_error_at = utc_now()
                await self.session.flush()

            # Режим Fail-Open: если включен и есть последнее сохранённое состояние в БД
            fail_open = False
            if hasattr(self.settings, "get_bool"):
                fail_open = await self.settings.get_bool("billing.fx.fail_open", False)
            elif hasattr(self.settings, "get"):
                raw_fo = await self.settings.get("billing.fx.fail_open")
                fail_open = str(raw_fo).lower() in ("1", "true", "yes") if raw_fo is not None else False
            last_rates_db = getattr(src, "last_rates", None) if is_orm else src.get("last_rates")

            if fail_open and last_rates_db:
                log.info("fx: fail-open active, using last saved rates from DB for source %r", src_id)
                fallback_rates = {
                    k: Decimal(str(v))
                    for k, v in last_rates_db.items()
                    if Decimal(str(v)) > 0
                }
                if fallback_rates:
                    await self._cache_for(cache_key, fallback_rates)
                    return fallback_rates

            raise

    async def rate_to_base(self, currency: str) -> Decimal:
        """Сколько базовой валюты стоит одна единица ``currency`` по цепочке приоритетов."""
        currency = (currency or "").strip().upper()
        base = await self.base_currency()
        if not currency or currency == base:
            return Decimal(1)

        last_error: Exception | None = None
        sources = await self.get_sources()

        for src in sources:
            is_orm = hasattr(src, "enabled")
            enabled = src.enabled if is_orm else src.get("enabled", True)
            if not enabled:
                continue

            try:
                rates = await self._rates_for_source(src)
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                continue

            if currency in rates:
                return rates[currency]

        if last_error is not None and isinstance(last_error, FxError):
            raise last_error
        raise FxError(f"no exchange rate for {currency} -> {base}")

    async def rate_from_base(self, currency: str) -> Decimal:
        """Сколько единиц ``currency`` стоит одна единица базовой валюты."""
        r = await self.rate_to_base(currency)
        if r <= Decimal("0"):
            raise FxError(f"invalid rate for {currency}")
        return Decimal(1) / r

    async def to_base(
        self, amount: Decimal, currency: str, locked_rate: Decimal | None = None
    ) -> tuple[Decimal, Decimal, str]:
        """Привести сумму к базовой валюте (обратная конвертация)."""
        base = await self.base_currency()
        curr = (currency or "").strip().upper()
        if not curr or curr == base:
            return amount.quantize(_CENT, rounding=ROUND_HALF_UP), Decimal(1), base

        if locked_rate is not None:
            rate = locked_rate
            converted = amount * rate
            return converted.quantize(_CENT, rounding=ROUND_HALF_UP), rate, base

        rate = await self.rate_to_base(currency)
        converted = amount * rate
        if rate != 1:
            markup = await self.settings.get_int("billing.fx.markup_percent", 0) or 0
            if markup:
                converted -= converted * Decimal(markup) / _HUNDRED
        return converted.quantize(_CENT, rounding=ROUND_HALF_UP), rate, base

    async def from_base(
        self, amount: Decimal, target_currency: str
    ) -> tuple[Decimal, Decimal]:
        """Конвертировать сумму из базовой валюты инстанса в целевую валюту оплаты."""
        base = await self.base_currency()
        target = (target_currency or "").strip().upper()
        if not target or target == base:
            return amount.quantize(_CENT, rounding=ROUND_HALF_UP), Decimal(1)

        rate_to_base = await self.rate_to_base(target)
        if rate_to_base <= Decimal("0"):
            raise FxError(f"invalid rate for {target}")

        target_amount = amount / rate_to_base
        markup = await self.settings.get_int("billing.fx.markup_percent", 0) or 0
        if markup:
            target_amount += target_amount * Decimal(markup) / _HUNDRED

        return target_amount.quantize(_CENT, rounding=ROUND_HALF_UP), rate_to_base

    async def get_available_currencies(self) -> set[str]:
        """Все валюты, для которых сейчас доступны курсы через активные источники (+ базовая)."""
        base = await self.base_currency()
        res = {base}
        sources = await self.get_sources()

        for src in sources:
            is_orm = hasattr(src, "enabled")
            enabled = src.enabled if is_orm else src.get("enabled", True)
            if not enabled:
                continue

            try:
                rates = await self._rates_for_source(src)
                res.update(rates.keys())
            except Exception:  # noqa: BLE001
                # Если упало, но в fail-open или last_rates есть данные
                last = getattr(src, "last_rates", None) if is_orm else src.get("last_rates")
                if last:
                    res.update(last.keys())

        return res

    async def test_source_config(
        self, source: dict[str, Any], base_override: str | None = None
    ) -> dict[str, Any]:
        """Протестировать конфигурацию источника без её сохранения."""
        base = (base_override or (await self.base_currency())).strip().upper()
        src_type = source.get("type")

        if src_type == "manual":
            raw_rates = source.get("rates")
            if not raw_rates and source.get("id") and self.session:
                from models.fx_sources import FxSourcesModel
                try:
                    src_id = int(source["id"])
                    src_db = await self.session.get(FxSourcesModel, src_id)
                    if src_db and src_db.rates:
                        raw_rates = src_db.rates
                except Exception:
                    pass
            if raw_rates and isinstance(raw_rates, dict) and len(raw_rates) > 0:
                return {
                    "ok": True,
                    "base": base,
                    "rates": {k: str(v) for k, v in raw_rates.items()},
                    "total": len(raw_rates),
                    "error": None,
                }
            rates = await self._manual_rates()
            return {
                "ok": True,
                "base": base,
                "rates": {k: str(v) for k, v in rates.items()},
                "total": len(rates),
                "error": None,
            }

        if src_type == "provider":
            prov_key = source.get("provider") or ""
            api_key = source.get("api_key") or ""
            if not api_key and source.get("id") and self.session and self.box:
                from models.fx_sources import FxSourcesModel
                try:
                    src_id = int(source["id"])
                    src_db = await self.session.get(FxSourcesModel, src_id)
                    if src_db and src_db.api_key_enc:
                        api_key = self.box.open(src_db.api_key_enc)
                except Exception:
                    pass
            provider = by_key(prov_key)
            if provider is None:
                return {"ok": False, "base": base, "rates": {}, "total": 0, "error": f"Неизвестный провайдер {prov_key!r}"}
            try:
                rates = await fetch_rates(provider, base, api_key)
                return {
                    "ok": True,
                    "base": base,
                    "rates": {k: str(v) for k, v in rates.items()},
                    "total": len(rates),
                    "error": None,
                }
            except Exception as exc:  # noqa: BLE001
                return {"ok": False, "base": base, "rates": {}, "total": 0, "error": str(exc)}

        if src_type == "lua":
            slug = source.get("lua_slug") or ""
            try:
                rates = await self._fetch_lua_rates(slug)
                return {
                    "ok": True,
                    "base": base,
                    "rates": {k: str(v) for k, v in rates.items()},
                    "total": len(rates),
                    "error": None,
                }
            except Exception as exc:  # noqa: BLE001
                return {"ok": False, "base": base, "rates": {}, "total": 0, "error": str(exc)}

        return {"ok": False, "base": base, "rates": {}, "total": 0, "error": f"Неизвестный тип источника {src_type!r}"}



    async def refresh_source(self, src: Any) -> dict[str, Decimal]:
        """Принудительно опросить источник (минуя кэш) и обновить его статус в БД."""
        is_orm = hasattr(src, "type")
        src_type = src.type if is_orm else src.get("type")
        src_id = src.id if is_orm else (src.get("id") or src_type or "default")

        if src_type == "manual":
            raw_rates = getattr(src, "rates", None) if is_orm else src.get("rates")
            out: dict[str, Decimal] = {}
            if raw_rates and isinstance(raw_rates, dict):
                for k, v in raw_rates.items():
                    try:
                        d = Decimal(str(v))
                        if d > 0:
                            out[str(k).strip().upper()] = d
                    except (ValueError, ArithmeticError):
                        continue
            if not out:
                out = await self._manual_rates()
            cache_key = f"{_CACHE_KEY_PREFIX}{src_id}"
            await self._cache_for(cache_key, out)
            if is_orm and self.session is not None:
                src.last_rates = {k: str(v) for k, v in out.items()}
                src.last_fetched_at = utc_now()
                src.last_error = None
                src.last_error_at = None
                await self.session.flush()
            return out

        cache_key = f"{_CACHE_KEY_PREFIX}{src_id}"
        api_key = ""
        if is_orm and getattr(src, "api_key_enc", None):
            api_key = self._decrypt_key(src.api_key_enc)
        if not api_key and not is_orm:
            api_key = src.get("api_key") or ""
        if not api_key:
            api_key = (await self.settings.get("billing.fx.api_key")) or ""

        try:
            if src_type == "provider":
                prov_key = src.provider if is_orm else (src.get("provider") or "")
                rates = await self._fetch_provider_rates(prov_key, api_key)
            elif src_type == "lua":
                slug = src.lua_slug if is_orm else (src.get("lua_slug") or "")
                rates = await self._fetch_lua_rates(slug)
            else:
                rates = {}

            await self._cache_for(cache_key, rates)
            if is_orm and self.session is not None:
                src.last_rates = {k: str(v) for k, v in rates.items()}
                src.last_fetched_at = utc_now()
                src.last_error = None
                src.last_error_at = None
                await self.session.flush()
            return rates
        except Exception as exc:
            log.warning("fx: refresh source %r failed: %s", src_id, exc)
            if is_orm and self.session is not None:
                src.last_error = str(exc)[:1024]
                src.last_error_at = utc_now()
                await self.session.flush()
            raise

    async def get_rates_overview(self) -> list[dict[str, Any]]:
        """Получить полный список всех доступных валют с их курсами к базовой и источником."""
        base = await self.base_currency()
        sources = await self.get_sources()
        resolved: dict[str, dict[str, Any]] = {}

        for src in sources:
            is_orm = hasattr(src, "enabled")
            enabled = src.enabled if is_orm else src.get("enabled", True)
            if not enabled:
                continue

            src_name = src.name if is_orm else (src.get("name") or src.get("provider") or src.get("type"))
            src_id = src.id if is_orm else src.get("id")
            src_priority = src.priority if is_orm else src.get("priority", 0)

            try:
                rates = await self._rates_for_source(src)
            except Exception:
                rates = getattr(src, "last_rates", None) if is_orm else src.get("last_rates")
                if not rates or not isinstance(rates, dict):
                    continue
                rates = {k: Decimal(str(v)) for k, v in rates.items() if str(v).replace('.', '', 1).isdigit()}

            for code, rate in rates.items():
                code_upper = str(code).strip().upper()
                if code_upper not in resolved and code_upper != base:
                    r_dec = Decimal(str(rate))
                    resolved[code_upper] = {
                        "currency": code_upper,
                        "rate_to_base": str(r_dec.quantize(Decimal("0.0001")) if r_dec < 1 else r_dec.quantize(Decimal("0.01"))),
                        "source_id": src_id,
                        "source_name": src_name,
                        "priority": src_priority,
                    }

        # Include base currency itself
        items = [
            {
                "currency": base,
                "rate_to_base": "1.00",
                "source_id": None,
                "source_name": "Базовая валюта",
                "priority": -1,
            }
        ]
        items.extend(sorted(resolved.values(), key=lambda x: x["currency"]))
        return items

__all__ = [
    "DEFAULT_CURRENCY",
    "FxError",
    "FxRates",
    "QUOTE_BASE_PER_UNIT",
    "QUOTE_UNIT_PER_BASE",
]
