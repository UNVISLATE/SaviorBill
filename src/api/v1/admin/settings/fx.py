"""Админ: источники курсов валют (/api/v1/admin/settings/fx).

Управление таблицей источников курсов `fx_sources` в БД, приоритетами (0..N),
проверкой источников в реальном времени, Fail-Open статусом и мониторингом ошибок.
"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.db import get_db_session
from dependencies.rbac import require_perm
from dependencies.sec import get_secbox
from dependencies.settings import SystemSettingsMngr, get_settings_mngr
from lua.bus import LuaBus
from lua.deps import get_lua_bus_configured
from models.fx_sources import FxSourcesModel
from models.user import UserModel
from security.sec.box import SecBox
from services.fx import DEFAULT_CURRENCY, FxRates
from services.fx_providers import PROVIDERS, by_key

router = APIRouter()

#: Сколько курсов показывать в ответе проверки — выборка для UI.
_PREVIEW_LIMIT = 24


class FxProviderOut(BaseModel):
    """Available exchange-rate provider."""

    key: str
    title: str
    needs_key: bool
    signup_url: str | None = None
    fixed_base: str | None = None
    note: str = ""


class FxSourceItem(BaseModel):
    """Элемент источника курсов."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str = Field(description="Type: 'provider' | 'lua' | 'manual'")
    name: str = Field(description="Display name")
    priority: int = Field(default=0, description="Priority index (0 = highest)")
    enabled: bool = Field(default=True, description="Whether the source is active")
    provider: str | None = Field(default=None, description="Provider key if type == 'provider'")
    has_api_key: bool = Field(default=False, description="Whether an encrypted API key is stored")
    script_id: int | None = Field(default=None, description="Lua script ID if type == 'lua'")
    lua_slug: str | None = Field(default=None, description="Lua script slug if type == 'lua'")
    rates: dict[str, str] = Field(default_factory=dict, description="Manual rates {CODE: RATE}")
    last_fetched_at: datetime | None = None
    last_error: str | None = None
    last_error_at: datetime | None = None
    last_rates_count: int = 0

    @classmethod
    def from_model(cls, m: FxSourcesModel) -> "FxSourceItem":
        rates = m.last_rates or {}
        manual_rates = m.rates or {}
        rates_count = len(manual_rates) if m.type == "manual" else (len(rates) if isinstance(rates, dict) else 0)
        return cls(
            id=m.id,
            type=m.type,
            name=m.name or m.provider or m.type,
            priority=m.priority,
            enabled=m.enabled,
            provider=m.provider,
            has_api_key=bool(m.api_key_enc),
            script_id=m.script_id,
            lua_slug=m.lua_slug,
            rates={k: str(v) for k, v in manual_rates.items()} if isinstance(manual_rates, dict) else {},
            last_fetched_at=m.last_fetched_at,
            last_error=m.last_error,
            last_error_at=m.last_error_at,
            last_rates_count=rates_count,
        )


class FxSourceCreate(BaseModel):
    """Create a new exchange-rate source in DB."""

    type: str = Field(description="Type: 'provider' | 'lua' | 'manual'")
    name: str = Field(default="", description="Display name")
    provider: str | None = Field(default=None, description="Provider key if type == 'provider'")
    api_key: str | None = Field(default=None, description="Plaintext API key to be encrypted (optional)")
    script_id: int | None = Field(default=None, description="Lua script ID if type == 'lua'")
    lua_slug: str | None = Field(default=None, description="Lua script slug if type == 'lua'")
    rates: dict[str, str] | None = Field(default=None, description="Manual rates {CODE: RATE}")
    enabled: bool = Field(default=True, description="Whether the source is active")


class FxSourcePatch(BaseModel):
    """Update an exchange-rate source."""

    name: str | None = None
    enabled: bool | None = None
    provider: str | None = None
    api_key: str | None = Field(default=None, description="New plaintext API key to encrypt")
    script_id: int | None = None
    lua_slug: str | None = None
    rates: dict[str, str] | None = None


class FxSourcesReorder(BaseModel):
    """Reorder sources by list of IDs in desired priority order (index 0 = highest)."""

    ids: list[int]


class FxTestIn(BaseModel):
    """Test an exchange-rate source without saving it first."""

    provider: str = Field(description="Provider key, or 'lua' for a script")
    api_key: str | None = Field(default=None, description="Overrides the stored key")
    base: str | None = Field(default=None, description="Overrides the instance base currency")


class FxTestSourceIn(BaseModel):
    """Test a full source configuration."""

    source: dict[str, Any]
    base: str | None = Field(default=None, description="Overrides the instance base currency")


class FxTestOut(BaseModel):
    """Result of an exchange-rate source probe."""

    ok: bool
    base: str
    rates: dict[str, str] = Field(default_factory=dict)
    total: int = 0
    error: str | None = None


class CurrencyStatusOut(BaseModel):
    """Статус возможности смены базовой валюты инстанса."""

    currency: str
    can_change: bool
    reason: str | None = None
    accounts_with_balance: int = 0
    total_balance: str = "0"
    total_bonus: str = "0"


class FxHealthOut(BaseModel):
    """Статус работоспособности источников курсов."""

    has_errors: bool
    count: int
    errors: list[dict[str, Any]] = Field(default_factory=list)


@router.get(
    "/currency-status",
    response_model=CurrencyStatusOut,
    dependencies=[Depends(require_perm("settings.raw.read"))],
    summary="Check if instance currency can be changed",
)
async def get_currency_status(
    session: AsyncSession = Depends(get_db_session),
    settings: SystemSettingsMngr = Depends(get_settings_mngr),
) -> CurrencyStatusOut:
    curr = (await settings.get("billing.currency")) or DEFAULT_CURRENCY
    stmt = select(
        func.count(UserModel.id),
        func.coalesce(func.sum(UserModel.balance), Decimal("0")),
        func.coalesce(func.sum(UserModel.bonus_balance), Decimal("0")),
    ).where(or_(UserModel.balance > 0, UserModel.bonus_balance > 0))
    count, sum_bal, sum_bon = (await session.execute(stmt)).one()
    if count > 0:
        return CurrencyStatusOut(
            currency=curr,
            can_change=False,
            reason=(
                f"У пользователей на балансе есть средства ({count} акк., "
                f"баланс: {sum_bal}, бонусы: {sum_bon}). "
                "Смена валюты заблокирована, пока все балансы не будут обнулены."
            ),
            accounts_with_balance=count,
            total_balance=str(sum_bal),
            total_bonus=str(sum_bon),
        )
    return CurrencyStatusOut(
        currency=curr,
        can_change=True,
        reason=None,
        accounts_with_balance=0,
        total_balance="0",
        total_bonus="0",
    )


@router.get(
    "/providers",
    response_model=list[FxProviderOut],
    dependencies=[Depends(require_perm("settings.raw.read"))],
    summary="Exchange-rate providers reference",
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


@router.get(
    "/sources",
    response_model=list[FxSourceItem],
    dependencies=[Depends(require_perm("settings.raw.read"))],
    summary="List all FX sources from database ordered by priority",
)
async def list_fx_sources(
    session: AsyncSession = Depends(get_db_session),
) -> list[FxSourceItem]:
    stmt = select(FxSourcesModel).order_by(FxSourcesModel.priority.asc(), FxSourcesModel.id.asc())
    rows = list(await session.scalars(stmt))
    return [FxSourceItem.from_model(r) for r in rows]


@router.post(
    "/sources",
    response_model=FxSourceItem,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_perm("settings.raw.edit"))],
    summary="Create a new FX source in database",
)
async def create_fx_source(
    body: FxSourceCreate,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    settings: SystemSettingsMngr = Depends(get_settings_mngr),
    bus: LuaBus = Depends(get_lua_bus_configured),
    box: SecBox = Depends(get_secbox),
) -> FxSourceItem:
    max_p = await session.scalar(select(func.coalesce(func.max(FxSourcesModel.priority), -1)))
    new_priority = (max_p or -1) + 1

    api_key_enc = ""
    if body.api_key and body.api_key.strip():
        api_key_enc = box.seal(body.api_key.strip())

    source = FxSourcesModel(
        type=body.type,
        name=body.name.strip() or (body.provider or body.type),
        priority=new_priority,
        enabled=body.enabled,
        provider=body.provider,
        api_key_enc=api_key_enc,
        script_id=body.script_id,
        lua_slug=body.lua_slug,
        rates=body.rates or {},
    )
    session.add(source)
    await session.flush()
    if source.enabled:
        try:
            fx = FxRates(settings, request.app.state.valkey, bus=bus, session=session, box=box)
            await fx.refresh_source(source)
        except Exception:
            pass
    await session.commit()
    return FxSourceItem.from_model(source)


@router.patch(
    "/sources/{source_id}",
    response_model=FxSourceItem,
    dependencies=[Depends(require_perm("settings.raw.edit"))],
    summary="Update an FX source",
)
async def update_fx_source(
    source_id: int,
    body: FxSourcePatch,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    settings: SystemSettingsMngr = Depends(get_settings_mngr),
    bus: LuaBus = Depends(get_lua_bus_configured),
    box: SecBox = Depends(get_secbox),
) -> FxSourceItem:
    source = await session.get(FxSourcesModel, source_id)
    if source is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "FX source not found")

    if body.name is not None:
        source.name = body.name.strip()
    if body.enabled is not None:
        source.enabled = body.enabled
    if body.provider is not None:
        source.provider = body.provider
    if body.script_id is not None:
        source.script_id = body.script_id
    if body.lua_slug is not None:
        source.lua_slug = body.lua_slug
    if body.rates is not None:
        source.rates = body.rates
    if body.api_key is not None:
        source.api_key_enc = box.seal(body.api_key.strip()) if body.api_key.strip() else ""

    await session.flush()
    if source.enabled:
        try:
            fx = FxRates(settings, request.app.state.valkey, bus=bus, session=session, box=box)
            await fx.refresh_source(source)
        except Exception:
            pass
    await session.commit()
    return FxSourceItem.from_model(source)


@router.delete(
    "/sources/{source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_perm("settings.raw.edit"))],
    summary="Delete an FX source",
)
async def delete_fx_source(
    source_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> None:
    source = await session.get(FxSourcesModel, source_id)
    if source is not None:
        await session.delete(source)
        await session.commit()


@router.put(
    "/sources/reorder",
    response_model=list[FxSourceItem],
    dependencies=[Depends(require_perm("settings.raw.edit"))],
    summary="Reorder FX sources priorities",
)
async def reorder_fx_sources(
    body: FxSourcesReorder,
    session: AsyncSession = Depends(get_db_session),
) -> list[FxSourceItem]:
    for idx, sid in enumerate(body.ids):
        source = await session.get(FxSourcesModel, sid)
        if source is not None:
            source.priority = idx
    await session.commit()

    stmt = select(FxSourcesModel).order_by(FxSourcesModel.priority.asc(), FxSourcesModel.id.asc())
    rows = list(await session.scalars(stmt))
    return [FxSourceItem.from_model(r) for r in rows]


@router.get(
    "/health",
    response_model=FxHealthOut,
    dependencies=[Depends(require_perm("settings.raw.read"))],
    summary="Check if any FX source has failed",
)
async def check_fx_health(
    session: AsyncSession = Depends(get_db_session),
) -> FxHealthOut:
    stmt = (
        select(FxSourcesModel)
        .where(FxSourcesModel.enabled.is_(True), FxSourcesModel.last_error.is_not(None))
    )
    failed = list(await session.scalars(stmt))
    errs = [
        {
            "id": s.id,
            "name": s.name,
            "provider": s.provider,
            "error": s.last_error,
            "error_at": s.last_error_at.isoformat() if s.last_error_at else None,
        }
        for s in failed
    ]
    return FxHealthOut(has_errors=bool(failed), count=len(failed), errors=errs)


@router.get(
    "/available-currencies",
    response_model=list[str],
    dependencies=[Depends(require_perm("settings.raw.read"))],
    summary="Get all currencies with valid exchange rates",
)
async def get_available_currencies(
    request: Request,
    settings: SystemSettingsMngr = Depends(get_settings_mngr),
    session: AsyncSession = Depends(get_db_session),
    bus: LuaBus = Depends(get_lua_bus_configured),
    box: SecBox = Depends(get_secbox),
) -> list[str]:
    fx = FxRates(settings, request.app.state.valkey, bus=bus, session=session, box=box)
    currencies = await fx.get_available_currencies()
    return sorted(currencies)


@router.post(
    "/test-source",
    response_model=FxTestOut,
    dependencies=[Depends(require_perm("settings.raw.edit"))],
    summary="Test any FX source configuration",
)
async def test_fx_source_config(
    request: Request,
    body: FxTestSourceIn,
    settings: SystemSettingsMngr = Depends(get_settings_mngr),
    session: AsyncSession = Depends(get_db_session),
    bus: LuaBus = Depends(get_lua_bus_configured),
    box: SecBox = Depends(get_secbox),
) -> FxTestOut:
    fx = FxRates(settings, request.app.state.valkey, bus=bus, session=session, box=box)
    res = await fx.test_source_config(body.source, base_override=body.base)
    preview = dict(sorted(res.get("rates", {}).items())[:_PREVIEW_LIMIT])
    return FxTestOut(
        ok=res.get("ok", False),
        base=res.get("base", "RUB"),
        rates=preview,
        total=res.get("total", 0),
        error=res.get("error"),
    )


@router.post(
    "/test",
    response_model=FxTestOut,
    dependencies=[Depends(require_perm("settings.raw.edit"))],
    summary="Probe a legacy exchange-rate provider",
)
async def test_fx_provider(
    request: Request,
    body: FxTestIn,
    settings: SystemSettingsMngr = Depends(get_settings_mngr),
    session: AsyncSession = Depends(get_db_session),
    bus: LuaBus = Depends(get_lua_bus_configured),
    box: SecBox = Depends(get_secbox),
) -> FxTestOut:
    fx = FxRates(settings, request.app.state.valkey, bus=bus, session=session, box=box)
    source_dict: dict[str, Any] = {
        "type": "lua" if body.provider == "lua" else "provider",
        "provider": body.provider,
        "api_key": body.api_key,
        "lua_slug": (await settings.get("billing.fx.lua_slug")) if body.provider == "lua" else None,
    }
    res = await fx.test_source_config(source_dict, base_override=body.base)
    preview = dict(sorted(res.get("rates", {}).items())[:_PREVIEW_LIMIT])
    return FxTestOut(
        ok=res.get("ok", False),
        base=res.get("base", "RUB"),
        rates=preview,
        total=res.get("total", 0),
        error=res.get("error"),
    )



@router.post(
    "/sources/{source_id}/refresh",
    response_model=FxSourceItem,
    dependencies=[Depends(require_perm("settings.raw.edit"))],
    summary="Force refresh an FX source",
)
async def refresh_fx_source(
    source_id: int,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    settings: SystemSettingsMngr = Depends(get_settings_mngr),
    bus: LuaBus = Depends(get_lua_bus_configured),
    box: SecBox = Depends(get_secbox),
) -> FxSourceItem:
    source = await session.get(FxSourcesModel, source_id)
    if source is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "FX source not found")
    fx = FxRates(settings, request.app.state.valkey, bus=bus, session=session, box=box)
    try:
        await fx.refresh_source(source)
    except Exception:
        pass
    await session.commit()
    return FxSourceItem.from_model(source)


@router.post(
    "/sources/refresh-all",
    response_model=list[FxSourceItem],
    dependencies=[Depends(require_perm("settings.raw.edit"))],
    summary="Force refresh all enabled FX sources",
)
async def refresh_all_fx_sources(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    settings: SystemSettingsMngr = Depends(get_settings_mngr),
    bus: LuaBus = Depends(get_lua_bus_configured),
    box: SecBox = Depends(get_secbox),
) -> list[FxSourceItem]:
    stmt = select(FxSourcesModel).where(FxSourcesModel.enabled.is_(True)).order_by(FxSourcesModel.priority.asc())
    sources = list(await session.scalars(stmt))
    fx = FxRates(settings, request.app.state.valkey, bus=bus, session=session, box=box)
    for s in sources:
        try:
            await fx.refresh_source(s)
        except Exception:
            pass
    await session.commit()
    stmt_all = select(FxSourcesModel).order_by(FxSourcesModel.priority.asc(), FxSourcesModel.id.asc())
    rows = list(await session.scalars(stmt_all))
    return [FxSourceItem.from_model(r) for r in rows]


@router.get(
    "/rates-overview",
    response_model=list[dict[str, Any]],
    dependencies=[Depends(require_perm("settings.raw.read"))],
    summary="Detailed overview of all available currencies with resolved exchange rates",
)
async def get_rates_overview(
    request: Request,
    settings: SystemSettingsMngr = Depends(get_settings_mngr),
    session: AsyncSession = Depends(get_db_session),
    bus: LuaBus = Depends(get_lua_bus_configured),
    box: SecBox = Depends(get_secbox),
) -> list[dict[str, Any]]:
    fx = FxRates(settings, request.app.state.valkey, bus=bus, session=session, box=box)
    return await fx.get_rates_overview()

__all__ = ["router"]
