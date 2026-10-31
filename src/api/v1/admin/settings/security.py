"""Админ: единый центр настроек безопасности (Rate Limits, Auto-Ban, Public Limits)."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
import valkey.asyncio as valkey

from core.config import AppConfig
from dependencies.ratelimit import LimitKind, _kind_setting_key, _rule_for
from dependencies.rbac import require_any_perm
from dependencies.settings import SystemSettingsMngr, get_settings_mngr
from dependencies.valkey import get_valkey_client
from schemas.ratelimit import RateLimitRule
from services.catalog_cache import invalidate_catalog_cache
from utils.public_pagination import snap_public_limit_setting

router = APIRouter()


class AutobanSettings(BaseModel):
    enabled: bool = True
    threshold: int = Field(default=5, ge=1, le=100)
    window_sec: int = Field(default=60, ge=5, le=3600)
    duration_sec: int = Field(default=900, ge=60, le=86400 * 30)


class CatalogPublicSettings(BaseModel):
    limit_max: int = Field(default=20, ge=1, le=200)
    limit_step: int = Field(default=10, description="Квантование: строго 5 или 10")
    cache_ttl_sec: int = Field(default=180, ge=10, le=86400)


class SecuritySettingsResponse(BaseModel):
    rate_limits: list[RateLimitRule]
    autoban: AutobanSettings
    catalog_public: CatalogPublicSettings


class SecuritySettingsPatch(BaseModel):
    autoban: AutobanSettings | None = None
    catalog_public: CatalogPublicSettings | None = None


@router.get(
    "",
    response_model=SecuritySettingsResponse,
    dependencies=[Depends(require_any_perm("settings.security.read", "settings.ratelimits.read"))],
    summary="Get unified security settings",
)
async def get_security_settings(
    request: Request,
    settings: SystemSettingsMngr = Depends(get_settings_mngr),
) -> SecuritySettingsResponse:
    cfg: AppConfig = request.app.state.settings

    # 1. Rate limits
    rules: list[RateLimitRule] = []
    for kind in LimitKind:
        base = _rule_for(cfg, kind)
        raw = await settings.get(_kind_setting_key(kind))
        if raw is not None:
            data = json.loads(raw)
            max_hits, window = int(data["max_hits"]), int(data["window"])
        else:
            max_hits, window = base.max_hits, base.window
        rules.append(
            RateLimitRule(
                kind=kind.value,
                max_hits=max_hits,
                window=window,
                overridden=raw is not None,
            )
        )

    # 2. Autoban
    autoban_enabled_raw = await settings.get("security.autoban.enabled", "1")
    autoban_enabled = autoban_enabled_raw.strip().lower() in ("1", "true", "yes", "on")
    autoban_threshold = int(await settings.get("security.autoban.threshold", "5"))
    autoban_window = int(await settings.get("security.autoban.window_sec", "60"))
    autoban_duration = int(await settings.get("security.autoban.duration_sec", "900"))

    autoban = AutobanSettings(
        enabled=autoban_enabled,
        threshold=autoban_threshold,
        window_sec=autoban_window,
        duration_sec=autoban_duration,
    )

    # 3. Public catalog pagination
    step_val = int(await settings.get("catalog.public.limit_step", "10"))
    limit_max_val = int(await settings.get("catalog.public.limit_max", "20"))
    ttl_val = int(await settings.get("cache.catalog.ttl_sec", "180"))

    catalog_public = CatalogPublicSettings(
        limit_max=limit_max_val,
        limit_step=step_val if step_val in (5, 10) else 10,
        cache_ttl_sec=ttl_val,
    )

    return SecuritySettingsResponse(
        rate_limits=rules,
        autoban=autoban,
        catalog_public=catalog_public,
    )


@router.put(
    "",
    response_model=SecuritySettingsResponse,
    dependencies=[Depends(require_any_perm("settings.security.edit", "settings.ratelimits.edit"))],
    summary="Update security settings",
)
async def update_security_settings(
    patch: SecuritySettingsPatch,
    request: Request,
    settings: SystemSettingsMngr = Depends(get_settings_mngr),
    vk: valkey.Valkey = Depends(get_valkey_client),
) -> SecuritySettingsResponse:
    if patch.autoban is not None:
        await settings.set("security.autoban.enabled", "1" if patch.autoban.enabled else "0")
        await settings.set("security.autoban.threshold", str(patch.autoban.threshold))
        await settings.set("security.autoban.window_sec", str(patch.autoban.window_sec))
        await settings.set("security.autoban.duration_sec", str(patch.autoban.duration_sec))

    if patch.catalog_public is not None:
        step = 5 if patch.catalog_public.limit_step == 5 else 10
        # Округление limit_max по ТЗ
        snapped_limit = snap_public_limit_setting(patch.catalog_public.limit_max, step)
        await settings.set("catalog.public.limit_step", str(step))
        await settings.set("catalog.public.limit_max", str(snapped_limit))
        await settings.set("cache.catalog.ttl_sec", str(patch.catalog_public.cache_ttl_sec))
        # Инвалидация кэша каталога
        await invalidate_catalog_cache(vk)

    return await get_security_settings(request, settings)


__all__ = ["router"]
