from __future__ import annotations

import valkey.asyncio as valkey
from fastapi import APIRouter, Depends, Request

from dependencies.ratelimit import LimitKind, _kind_keys, _rule_for
from dependencies.rbac import require_perm
from dependencies.valkey import get_valkey_client
from schemas.ratelimit import RateLimitPatch, RateLimitRule
from utils.apidoc import with_fields
from utils.config import AppConfig

router = APIRouter()


@router.get(
    "/settings/ratelimits",
    response_model=list[RateLimitRule],
    dependencies=[Depends(require_perm("settings.ratelimits.read"))],
    summary="Текущие лимиты частоты запросов",
)
async def list_rate_limits(
    request: Request,
    vk: valkey.Valkey = Depends(get_valkey_client),
) -> list[RateLimitRule]:
    """Действующие правила по категориям (с пометкой ручного переопределения)."""
    cfg: AppConfig = request.app.state.settings
    out: list[RateLimitRule] = []
    for kind in LimitKind:
        kmax, kwin = _kind_keys(kind)
        vmax, vwin = await vk.mget([kmax, kwin])
        base = _rule_for(cfg, kind)
        # Считаем «переопределением» лишь несовпадение с ENV-дефолтом.
        max_hits = int(vmax) if vmax is not None else base.max_hits
        window = int(vwin) if vwin is not None else base.window
        overridden = max_hits != base.max_hits or window != base.window
        out.append(
            RateLimitRule(
                kind=kind.value,
                max_hits=max_hits,
                window=window,
                overridden=overridden,
            )
        )
    return out


@router.put(
    "/settings/ratelimits/{kind}",
    response_model=RateLimitRule,
    dependencies=[Depends(require_perm("settings.ratelimits.edit"))],
    summary="Переопределить лимит категории",
    description=with_fields(
        "Задаёт лимит для категории (default/auth/mail/sensitive) в рантайме без "
        "рестарта. Применяется сразу ко всем роутам этой категории.",
        RateLimitPatch,
    ),
)
async def set_rate_limit(
    kind: LimitKind,
    body: RateLimitPatch,
    vk: valkey.Valkey = Depends(get_valkey_client),
) -> RateLimitRule:
    """Записать переопределение правила категории в Valkey."""
    kmax, kwin = _kind_keys(kind)
    await vk.set(kmax, body.max_hits)
    await vk.set(kwin, body.window)
    return RateLimitRule(
        kind=kind.value,
        max_hits=body.max_hits,
        window=body.window,
        overridden=True,
    )


@router.delete(
    "/settings/ratelimits/{kind}",
    response_model=RateLimitRule,
    dependencies=[Depends(require_perm("settings.ratelimits.delete"))],
    summary="Сбросить лимит категории к ENV-дефолту",
)
async def reset_rate_limit(
    kind: LimitKind,
    request: Request,
    vk: valkey.Valkey = Depends(get_valkey_client),
) -> RateLimitRule:
    """Удалить переопределение — вернуться к значению из ENV."""
    cfg: AppConfig = request.app.state.settings
    kmax, kwin = _kind_keys(kind)
    base = _rule_for(cfg, kind)
    await vk.set(kmax, base.max_hits)
    await vk.set(kwin, base.window)
    return RateLimitRule(
        kind=kind.value,
        max_hits=base.max_hits,
        window=base.window,
        overridden=False,
    )


__all__ = ["router"]
