"""Админ: источники курсов валют (/api/v1/admin/settings/fx).

Список готовых провайдеров для выпадающего списка и «проба пера» — запрос к
выбранному источнику прямо сейчас, с показом разобранных курсов. Без этого
настроить курсы можно было только вслепую: ошибка в ключе или формате
всплывала уже на живом платеже.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.db import get_db_session
from dependencies.rbac import require_perm
from dependencies.settings import SystemSettingsMngr, get_settings_mngr
from lua.bus import LuaBus
from lua.deps import get_lua_bus_configured
from services.fx import FxRates
from services.fx_providers import PROVIDERS, FxProviderError, by_key, fetch_rates

router = APIRouter()

#: Сколько курсов показывать в ответе проверки — не весь список из полутора
#: сотен валют, а достаточную для проверки формата выборку.
_PREVIEW_LIMIT = 12


class FxProviderOut(BaseModel):
    """Available exchange-rate provider."""

    key: str
    title: str
    needs_key: bool
    signup_url: str | None = None
    fixed_base: str | None = None
    note: str = ""


class FxTestIn(BaseModel):
    """Test an exchange-rate source without saving it first."""

    provider: str = Field(description="Provider key, or 'lua' for a script")
    api_key: str | None = Field(default=None, description="Overrides the stored key")
    base: str | None = Field(default=None, description="Overrides the instance base currency")


class FxTestOut(BaseModel):
    """Result of an exchange-rate source probe."""

    ok: bool
    base: str
    #: Разобранные курсы: сколько базовой валюты за единицу указанной.
    rates: dict[str, str] = Field(default_factory=dict)
    total: int = 0
    error: str | None = None


@router.get(
    "/providers",
    response_model=list[FxProviderOut],
    dependencies=[Depends(require_perm("settings.raw.read"))],
    summary="Exchange-rate providers",
)
async def list_fx_providers() -> list[FxProviderOut]:
    return [
        FxProviderOut(
            key=p.key,
            title=p.title,
            needs_key=p.needs_key,
            signup_url=p.signup_url,
            fixed_base=p.fixed_base,
            note=p.note,
        )
        for p in PROVIDERS
    ]


@router.post(
    "/test",
    response_model=FxTestOut,
    dependencies=[Depends(require_perm("settings.raw.edit"))],
    summary="Probe an exchange-rate source",
    description="Fetches rates right now and returns what the server parsed. "
    "Never raises on a bad source — the failure is reported in `error` so the "
    "UI can show it inline.",
)
async def test_fx_provider(
    request: Request,
    body: FxTestIn,
    settings: SystemSettingsMngr = Depends(get_settings_mngr),
    session: AsyncSession = Depends(get_db_session),
    bus: LuaBus = Depends(get_lua_bus_configured),
) -> FxTestOut:
    fx = FxRates(settings, request.app.state.valkey, bus=bus, session=session)
    base = (body.base or await fx.base_currency()).strip().upper()

    try:
        if body.provider == "lua":
            rates: dict[str, Decimal] = await fx._lua_rates()  # noqa: SLF001 — свой же сервис
        else:
            provider = by_key(body.provider)
            if provider is None:
                return FxTestOut(ok=False, base=base, error=f"неизвестный провайдер {body.provider!r}")
            api_key = body.api_key or (await settings.get("billing.fx.api_key")) or ""
            rates = await fetch_rates(provider, base, api_key)
    except FxProviderError as exc:
        return FxTestOut(ok=False, base=base, error=str(exc))
    except Exception as exc:  # noqa: BLE001 — проверка не должна ронять запрос
        return FxTestOut(ok=False, base=base, error=f"{type(exc).__name__}: {exc}")

    preview = dict(sorted(rates.items())[:_PREVIEW_LIMIT])
    return FxTestOut(
        ok=True,
        base=base,
        rates={code: str(rate) for code, rate in preview.items()},
        total=len(rates),
    )


__all__ = ["router"]
