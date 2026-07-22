from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request

from dependencies.ratelimit import LimitKind, _kind_setting_key, _rule_for
from dependencies.rbac import require_perm
from dependencies.settings import SystemSettingsMngr, get_settings_mngr
from schemas.ratelimit import RateLimitPatch, RateLimitRule
from core.config import AppConfig

router = APIRouter()


@router.get(
    "",
    response_model=list[RateLimitRule],
    dependencies=[Depends(require_perm("settings.ratelimits.read"))],
    summary="Rate limits",
)
async def list_rate_limits(
    request: Request,
    settings: SystemSettingsMngr = Depends(get_settings_mngr),
) -> list[RateLimitRule]:
    """Действующие правила по категориям (с пометкой ручного переопределения)."""
    cfg: AppConfig = request.app.state.settings
    out: list[RateLimitRule] = []
    for kind in LimitKind:
        base = _rule_for(cfg, kind)
        raw = await settings.get(_kind_setting_key(kind))
        if raw is not None:
            data = json.loads(raw)
            max_hits, window = int(data["max_hits"]), int(data["window"])
        else:
            max_hits, window = base.max_hits, base.window
        out.append(
            RateLimitRule(
                kind=kind.value,
                max_hits=max_hits,
                window=window,
                overridden=raw is not None,
            )
        )
    return out


@router.put(
    "/{kind}",
    response_model=RateLimitRule,
    dependencies=[Depends(require_perm("settings.ratelimits.edit"))],
    summary="Set rate limit",
    description="Override a rate limit at runtime.",
)
async def set_rate_limit(
    kind: LimitKind,
    body: RateLimitPatch,
    settings: SystemSettingsMngr = Depends(get_settings_mngr),
) -> RateLimitRule:
    """Записать переопределение правила категории в таблицу settings."""
    await settings.set(
        _kind_setting_key(kind),
        json.dumps({"max_hits": body.max_hits, "window": body.window}),
    )
    return RateLimitRule(
        kind=kind.value,
        max_hits=body.max_hits,
        window=body.window,
        overridden=True,
    )


@router.delete(
    "/{kind}",
    response_model=RateLimitRule,
    dependencies=[Depends(require_perm("settings.ratelimits.edit"))],
    summary="Reset rate limit",
)
async def reset_rate_limit(
    kind: LimitKind,
    request: Request,
    settings: SystemSettingsMngr = Depends(get_settings_mngr),
) -> RateLimitRule:
    """Удалить переопределение — вернуться к значению из ENV."""
    cfg: AppConfig = request.app.state.settings
    base = _rule_for(cfg, kind)
    await settings.set(_kind_setting_key(kind), None)
    return RateLimitRule(
        kind=kind.value,
        max_hits=base.max_hits,
        window=base.window,
        overridden=False,
    )


__all__ = ["router"]
