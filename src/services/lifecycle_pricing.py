"""Сервис расчёта и валидации продления/апгрейда выданной услуги."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from fastapi import HTTPException, status

from enums import PriceType, UsvcStatus
from models.service import ServiceModel
from services.pricing import ResolvedOrder, resolve_service_order
from utils.datetime_utils import utc_now

_CENT = Decimal("0.01")


@dataclass
class RenewQuote:
    """Результат расчёта продления услуги."""

    price: Decimal
    duration: int
    resolved: ResolvedOrder
    config_changed: bool


def _extract_current_tier_and_components(usvc) -> tuple[str | None, dict[str, Any] | None]:
    cfg = dict(getattr(usvc, "order_config", None) or {})
    tier = cfg.get("tier")
    tier_code = tier.get("code") if isinstance(tier, dict) else None

    comps_raw = cfg.get("components")
    components: dict[str, Any] | None = None
    if isinstance(comps_raw, dict):
        components = {}
        for k, v in comps_raw.items():
            if isinstance(v, dict) and "value" in v:
                components[k] = v["value"]
            else:
                components[k] = v
    return tier_code, components


def _configs_differ(
    usvc_cfg: dict,
    new_cfg: dict,
) -> bool:
    """Проверить, изменился ли тариф или компоненты по сравнению с текущим order_config."""
    old_tier = (usvc_cfg.get("tier") or {}).get("code") if isinstance(usvc_cfg.get("tier"), dict) else None
    new_tier = (new_cfg.get("tier") or {}).get("code") if isinstance(new_cfg.get("tier"), dict) else None
    if old_tier != new_tier:
        return True

    def _norm_comps(c: Any) -> dict[str, Any]:
        if not isinstance(c, dict):
            return {}
        out: dict[str, Any] = {}
        for k, v in c.items():
            out[k] = v.get("value") if isinstance(v, dict) and "value" in v else v
        return out

    return _norm_comps(usvc_cfg.get("components")) != _norm_comps(new_cfg.get("components"))


def assert_renew_allowed(
    usvc,
    service: ServiceModel,
    *,
    now: datetime | None = None,
    duration_sec: int | None = None,
) -> None:
    """Проверить применимость преждевременного продления к услуге и её текущему статусу."""
    now = now or utc_now()
    settings = dict(getattr(service, "settings", None) or {})
    if not settings.get("allow_early_renew", False):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "early renewal is not enabled for this service",
        )
    is_archived = bool(settings.get("is_archived", False))
    if (not service.is_active or is_archived) and not settings.get("allow_renew_when_archived", False):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "renewal is not available for archived or inactive service",
        )
    if usvc.status not in (UsvcStatus.ACTIVE, UsvcStatus.STOPPED, UsvcStatus.EXPIRED):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"service cannot be renewed in status '{usvc.status}'",
        )

    if usvc.status == UsvcStatus.EXPIRED and usvc.expires_at is not None:
        grace = settings.get("renew_grace_period_sec")
        if grace is not None:
            if (now - usvc.expires_at).total_seconds() > int(grace):
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    "renewal grace period has expired",
                )

    early_window = settings.get("early_renew_window_sec")
    if (
        early_window is not None
        and usvc.status in (UsvcStatus.ACTIVE, UsvcStatus.STOPPED)
        and usvc.expires_at is not None
    ):
        remaining = (usvc.expires_at - now).total_seconds()
        if remaining > int(early_window):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "too early to renew this service",
            )

    max_ahead = settings.get("max_expires_ahead_sec")
    if max_ahead is not None and duration_sec:
        base_exp = (
            usvc.expires_at
            if (usvc.status in (UsvcStatus.ACTIVE, UsvcStatus.STOPPED) and usvc.expires_at and usvc.expires_at > now)
            else now
        )
        new_exp = base_exp + timedelta(seconds=duration_sec)
        if (new_exp - now).total_seconds() > int(max_ahead):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "maximum prepayment horizon exceeded",
            )


def resolve_renew_quote(
    usvc,
    service: ServiceModel,
    *,
    tier_code: str | None = None,
    components: dict[str, Any] | None = None,
) -> RenewQuote:
    """Рассчитать стоимость и длительность продления существующей услуги."""
    settings = dict(getattr(service, "settings", None) or {})
    cur_tier, cur_comps = _extract_current_tier_and_components(usvc)
    usvc_cfg = dict(getattr(usvc, "order_config", None) or {})

    target_tier = tier_code if tier_code is not None else cur_tier
    target_comps = components if components is not None else cur_comps

    price_type = getattr(service, "price_type", PriceType.FIXED) or PriceType.FIXED
    custom_amt: Decimal | None = None
    if price_type == PriceType.CUSTOM:
        nom = usvc_cfg.get("nominal_amount") or usvc_cfg.get("amount") or getattr(usvc, "price", None)
        custom_amt = Decimal(str(nom)) if nom is not None else None

    resolved = resolve_service_order(
        service,
        custom_amount=custom_amt,
        tier_code=target_tier,
        components=target_comps,
        form=usvc_cfg.get("form") if isinstance(usvc_cfg.get("form"), dict) else None,
    )

    config_changed = _configs_differ(usvc_cfg, resolved.order_config)
    if config_changed and not settings.get("allow_renew_config_change", False):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "changing plan or components on renewal is not enabled for this service",
        )

    policy = str(settings.get("renew_price_policy") or "current").strip().lower()
    if policy == "locked" and not config_changed:
        base_price = Decimal(str(getattr(usvc, "price", resolved.price) or resolved.price))
        if base_price <= Decimal("0"):
            base_price = resolved.price
        duration = getattr(usvc, "duration", None) or resolved.duration
    else:
        base_price = resolved.price
        duration = resolved.duration

    if not duration or int(duration) <= 0:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "service has no billing duration to renew",
        )

    return RenewQuote(
        price=base_price.quantize(_CENT, rounding=ROUND_HALF_UP),
        duration=int(duration),
        resolved=resolved,
        config_changed=config_changed,
    )


__all__ = ["RenewQuote", "assert_renew_allowed", "resolve_renew_quote"]
