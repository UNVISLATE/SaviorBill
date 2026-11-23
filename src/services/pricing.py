"""Сервис расчёта цен и валидации параметров заказа (Услуги 2.0)."""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException, status

from enums import PriceType

if TYPE_CHECKING:
    from models.service import ServiceModel


def deep_merge(base: dict, override: dict) -> dict:
    """Рекурсивное слияние словарей: override перекрывает base."""
    merged = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if k in merged and isinstance(merged[k], dict) and isinstance(v, dict):
            merged[k] = deep_merge(merged[k], v)
        else:
            merged[k] = copy.deepcopy(v)
    return merged


def set_dot_path(target: dict, path: str, value: Any) -> None:
    """Установка значения по точечному пути (например, 'resources.vcpu')."""
    parts = path.strip().split(".")
    curr = target
    for p in parts[:-1]:
        if p not in curr or not isinstance(curr[p], dict):
            curr[p] = {}
        curr = curr[p]
    curr[parts[-1]] = value


def unflatten_dot_dict(flat: dict) -> dict:
    """Преобразование плоского словаря с точечными ключами в древовидный.

    {'steam.login': 'user'} -> {'steam': {'login': 'user'}}
    """
    res: dict[str, Any] = {}
    for k, v in (flat or {}).items():
        set_dot_path(res, k, v)
    return res


def validate_order_form(
    pricing_config: dict[str, Any],
    client_form: dict[str, Any] | None,
    service: Any = None,
) -> dict[str, Any]:
    """Валидация формы заказа покупателя по манифесту SBUI или списку полей."""
    manifest_data = pricing_config.get("manifest")
    if not manifest_data and service is not None:
        lua_script = getattr(service, "lua_script", None)
        if lua_script and getattr(lua_script, "settings", None) and isinstance(lua_script.settings, dict):
            manifest_data = lua_script.settings.get("manifest")

    if manifest_data and isinstance(manifest_data, dict):
        client_order_form = manifest_data.get("client_order_form")
        if client_order_form:
            from schemas.manifest import FieldDefinition, ScriptManifest
            from services.manifest import validate_client_order_form

            parsed_fields = []
            for raw_fld in client_order_form:
                try:
                    parsed_fields.append(
                        FieldDefinition.model_validate(raw_fld)
                        if isinstance(raw_fld, dict)
                        else raw_fld
                    )
                except Exception:
                    continue
            safe_manifest = ScriptManifest(
                name=str(manifest_data.get("name") or "Service"),
                slug=str(manifest_data.get("slug") or "service"),
                client_order_form=parsed_fields,
            )
            return validate_client_order_form(safe_manifest, client_form)
        return {}

    # Валидация по полям legacy-конфигурации формы
    form_defs = pricing_config.get("form")
    if not form_defs:
        return {}

    validated_form: dict[str, Any] = {}
    c_form = client_form or {}
    for fld in form_defs:
        fld_key = fld.get("key") or fld.get("id")
        if not fld_key:
            continue
        val = c_form.get(fld_key)
        if fld.get("required") and (val is None or not str(val).strip()):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"form field {fld_key!r} ({fld.get('label') or fld_key}) is required",
            )
        if val is not None:
            val_str = str(val).strip()
            regex_pat = fld.get("regex")
            if regex_pat:
                try:
                    if not re.match(regex_pat, val_str):
                        raise HTTPException(
                            status.HTTP_400_BAD_REQUEST,
                            fld.get("regex_error")
                            or f"field {fld_key!r} does not match required format",
                        )
                except re.error:
                    pass
            validated_form[fld_key] = val_str
    return validated_form


@dataclass
class ResolvedOrder:
    """Результат авторитарного расчёта заказа сервером."""

    price: Decimal
    duration: int | None
    effective_settings: dict
    order_config: dict


def resolve_service_order(
    service: ServiceModel,
    *,
    custom_amount: Decimal | None = None,
    tier_code: str | None = None,
    components: dict[str, Any] | None = None,
    form: dict[str, Any] | None = None,
) -> ResolvedOrder:
    """Авторитетный серверный расчёт стоимости, срока и настроек услуги.

    Вызывается перед созданием заказа или счёта на оплату.
    Гарантирует принцип Zero Trust to Client.
    """
    price_type = getattr(service, "price_type", PriceType.FIXED) or PriceType.FIXED
    pricing_config = getattr(service, "pricing_config", {}) or {}

    # 1. FIXED
    if price_type == PriceType.FIXED:
        validated_form = validate_order_form(pricing_config, form, service=service)
        order_config = {"form": validated_form} if validated_form else {}
        return ResolvedOrder(
            price=service.price,
            duration=service.duration,
            effective_settings=dict(getattr(service, "settings", None) or {}),
            order_config=order_config,
        )

    # 2. CUSTOM (Steam-пополнения, донаты, произвольные суммы)
    elif price_type == PriceType.CUSTOM:
        if custom_amount is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "custom_amount is required for service with custom pricing",
            )
        min_amt = Decimal(str(pricing_config.get("min", "0.01")))
        max_amt = Decimal(str(pricing_config.get("max", "999999999")))
        if custom_amount < min_amt or custom_amount > max_amt:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"custom_amount must be between {min_amt} and {max_amt}",
            )
        step = pricing_config.get("step")
        if step is not None:
            step_dec = Decimal(str(step))
            if step_dec > 0 and ((custom_amount - min_amt) % step_dec) != Decimal("0"):
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    f"custom_amount must be a multiple of {step_dec} starting from {min_amt}",
                )

        validated_form = validate_order_form(pricing_config, form, service=service)

        markup_percent_raw = pricing_config.get("markup_percent")
        markup_fixed_raw = pricing_config.get("markup_fixed")

        markup_percent = Decimal(str(markup_percent_raw)) if markup_percent_raw not in (None, "") else Decimal("0")
        markup_fixed = Decimal(str(markup_fixed_raw)) if markup_fixed_raw not in (None, "") else Decimal("0")

        markup_amount = Decimal("0")
        if markup_percent > Decimal("0"):
            markup_amount += (custom_amount * markup_percent / Decimal("100"))
        if markup_fixed > Decimal("0"):
            markup_amount += markup_fixed

        markup_amount = markup_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        charge_amount = (custom_amount + markup_amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        order_config = {
            "amount": str(charge_amount),
            "nominal_amount": str(custom_amount),
            "markup_amount": str(markup_amount),
            "form": validated_form,
        }
        if markup_percent > Decimal("0"):
            order_config["markup_percent"] = str(markup_percent)
        if markup_fixed > Decimal("0"):
            order_config["markup_fixed"] = str(markup_fixed)
        if pricing_config.get("allow_sub_nominal_discount") is not None:
            order_config["allow_sub_nominal_discount"] = bool(pricing_config.get("allow_sub_nominal_discount"))
        if pricing_config.get("max_loss_percent") not in (None, "", "0", 0):
            order_config["max_loss_percent"] = str(pricing_config.get("max_loss_percent"))

        return ResolvedOrder(
            price=charge_amount,
            duration=service.duration,
            effective_settings=dict(getattr(service, "settings", None) or {}),
            order_config=order_config,
        )

    # 3. TIERED (VPN, подписки, сетки периодов и планов)
    elif price_type == PriceType.TIERED:
        if not tier_code:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "tier_code is required for tiered service",
            )
        matched_plan: dict | None = None
        matched_group: dict | None = None
        for item in pricing_config.get("tiers", []):
            if isinstance(item, dict) and "subtiers" in item:
                # Grouped structure
                for subtier in item.get("subtiers", []):
                    if isinstance(subtier, dict) and subtier.get("code") == tier_code:
                        matched_plan = subtier
                        matched_group = {
                            "code": item.get("code"),
                            "title": item.get("title"),
                        }
                        break
            elif isinstance(item, dict):
                # Flat plan structure
                if item.get("code") == tier_code:
                    matched_plan = item
                    if item.get("group"):
                        matched_group = {
                            "code": item.get("group"),
                            "title": item.get("group"),
                        }
                    break
            if matched_plan is not None:
                break

        if matched_plan is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"tier_code {tier_code!r} not found in service pricing config",
            )

        tier_price = Decimal(str(matched_plan["price"]))
        duration_seconds = matched_plan.get("duration_seconds")
        duration_days = matched_plan.get("duration_days")
        if duration_seconds is not None:
            duration_sec = int(duration_seconds)
        elif duration_days is not None:
            duration_sec = int(duration_days) * 86400
        else:
            duration_sec = service.duration
        settings_override = matched_plan.get("settings_override") or {}
        effective_settings = deep_merge(dict(service.settings or {}), settings_override)

        tier_dict: dict[str, Any] = {
            "code": matched_plan.get("code"),
            "title": matched_plan.get("title"),
            "duration_days": duration_days,
            "duration_seconds": duration_seconds,
        }
        order_config: dict[str, Any] = {"tier": tier_dict}
        if matched_group:
            order_config["group"] = matched_group
            tier_dict["group"] = matched_group.get("title")
        validated_form = validate_order_form(pricing_config, form, service=service)
        if validated_form:
            order_config["form"] = validated_form
        return ResolvedOrder(
            price=tier_price,
            duration=duration_sec,
            effective_settings=effective_settings,
            order_config=order_config,
        )

    # 4. CONFIGURABLE (VDS, хостинг, калькулятор компонентов)
    elif price_type == PriceType.CONFIGURABLE:
        components_input = components or {}
        total_price = service.price
        effective_settings = copy.deepcopy(getattr(service, "settings", None) or {})
        resolved_components: dict[str, Any] = {}

        for comp in pricing_config.get("components", []):
            comp_code = comp.get("code")
            if not comp_code:
                continue
            comp_type = comp.get("type", "slider")
            path = comp.get("path")
            user_val = components_input.get(comp_code)
            if user_val is None:
                user_val = comp.get("default", "0")

            if comp_type == "select":
                opt_match = None
                for opt in comp.get("options", []):
                    if str(opt.get("value")) == str(user_val):
                        opt_match = opt
                        break
                if opt_match is None:
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST,
                        f"invalid option {user_val!r} for component {comp_code!r}",
                    )
                delta = Decimal(str(opt_match.get("price_delta", "0")))
                total_price += delta
                if path:
                    set_dot_path(effective_settings, path, opt_match["value"])
                resolved_components[comp_code] = {
                    "value": opt_match["value"],
                    "label": opt_match.get("label", opt_match["value"]),
                    "price_delta": str(delta),
                }
            elif comp_type == "switch":
                if isinstance(user_val, bool):
                    bool_val = user_val
                elif isinstance(user_val, (int, Decimal)) and user_val in (0, 1):
                    bool_val = bool(user_val)
                elif isinstance(user_val, str) and user_val.strip().lower() in (
                    "true",
                    "1",
                    "yes",
                    "on",
                ):
                    bool_val = True
                elif isinstance(user_val, str) and user_val.strip().lower() in (
                    "false",
                    "0",
                    "no",
                    "off",
                    "",
                ):
                    bool_val = False
                else:
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST,
                        f"component {comp_code!r} must be a boolean",
                    )
                unit_price = Decimal(str(comp.get("unit_price", "0")))
                delta = unit_price if bool_val else Decimal("0")
                total_price += delta
                if path:
                    set_dot_path(effective_settings, path, bool_val)
                resolved_components[comp_code] = {
                    "value": bool_val,
                    "unit": comp.get("unit", ""),
                    "unit_price": str(unit_price),
                    "price_delta": str(delta),
                }
            else:
                try:
                    num_val = Decimal(str(user_val))
                except Exception:
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST,
                        f"component {comp_code!r} must be a number",
                    )
                min_v = comp.get("min")
                if min_v is not None and num_val < Decimal(str(min_v)):
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST,
                        f"component {comp_code!r} value {num_val} is less than min {min_v}",
                    )
                max_v = comp.get("max")
                if max_v is not None and num_val > Decimal(str(max_v)):
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST,
                        f"component {comp_code!r} value {num_val} exceeds max {max_v}",
                    )
                step_v = comp.get("step")
                if step_v is not None:
                    step_dec = Decimal(str(step_v))
                    base_v = Decimal(str(min_v)) if min_v is not None else Decimal("0")
                    if step_dec > 0 and ((num_val - base_v) % step_dec) != Decimal("0"):
                        raise HTTPException(
                            status.HTTP_400_BAD_REQUEST,
                            f"component {comp_code!r} value {num_val} must be a multiple of {step_dec}",
                        )
                unit_price = Decimal(str(comp.get("unit_price", "0")))
                delta = num_val * unit_price
                total_price += delta
                val_to_set = int(num_val) if num_val % 1 == 0 else float(num_val)
                if path:
                    set_dot_path(effective_settings, path, val_to_set)
                resolved_components[comp_code] = {
                    "value": val_to_set,
                    "unit": comp.get("unit", ""),
                    "unit_price": str(unit_price),
                    "price_delta": str(delta),
                }

        validated_form = validate_order_form(pricing_config, form, service=service)
        order_config = {
            "components": resolved_components,
        }
        if validated_form:
            order_config["form"] = validated_form
        return ResolvedOrder(
            price=total_price,
            duration=service.duration,
            effective_settings=effective_settings,
            order_config=order_config,
        )

    else:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"unsupported price_type: {price_type!r}",
        )


def assert_promotions_allowed(service: Any) -> None:
    """Проверить, разрешены ли промокоды и скидки для услуги."""
    if (getattr(service, "settings", None) or {}).get("allow_promotions", True) is False:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "service does not participate in promotions",
        )


def apply_discount_with_floor(
    service: Any,
    resolved: ResolvedOrder,
    discount: Decimal,
    *,
    custom_amount: Decimal | None = None,
) -> Decimal:
    """Рассчитать итоговую цену после скидки с учётом защиты номинала для ``PriceType.CUSTOM``."""
    base_price = resolved.price
    clamped = max(Decimal("0"), min(discount, base_price))
    price_type = getattr(service, "price_type", PriceType.FIXED) or PriceType.FIXED
    if price_type == PriceType.CUSTOM:
        nominal_amount = Decimal(
            str(resolved.order_config.get("nominal_amount") or custom_amount or base_price)
        )
        allow_sub_nominal = bool(
            resolved.order_config.get("allow_sub_nominal_discount", False)
        )
        if not allow_sub_nominal:
            return max(base_price - clamped, nominal_amount)
        max_loss_p = Decimal(
            str(resolved.order_config.get("max_loss_percent", "0") or "0")
        )
        min_floor = max(
            Decimal("0.01"),
            (
                nominal_amount * (Decimal("1") - max_loss_p / Decimal("100"))
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        )
        return max(base_price - clamped, min_floor)
    return base_price - clamped
