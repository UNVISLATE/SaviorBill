from __future__ import annotations

"""Выданные услуги текущего пользователя (/api/v1/user/services)."""

import logging
import re

logger = logging.getLogger(__name__)

from decimal import Decimal

import valkey.asyncio as valkey
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import Text, cast, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.auth import get_current_acc
from dependencies.catalog import ServiceMngr, get_service_mngr
from dependencies.db import get_db_session
from dependencies.email import get_email_sender
from dependencies.promo import PromoCodesMngr, get_promo_mngr
from dependencies.rbac import require_perm
from dependencies.ratelimit import LimitKind, rate_limit
from dependencies.sec import make_secbox
from dependencies.triggers import get_dispatcher
from dependencies.usersvc import UserServicesMngr, get_usersvc_mngr
from dependencies.valkey import get_valkey_client
from enums import UsvcStatus, PromoKind, ServiceAction
from lifecycle.notifications import EmailSender
from lifecycle.triggers import TriggerDispatcher, TriggerEvent
from models.service import ServiceModel
from models.user import UserModel
from models.user_services import UserServicesModel
from schemas.manifest import CustomActionVerify
from schemas.orders import (
    OrderCreate,
    Order,
    OrderActionRequest,
    OrderActionChallengeRequest,
    OrderAutoRenewRequest,
    OrderRenewRequest,
    OrderUpgradeRequest,
)
from schemas.page import Page
from services.account import lock_account
from services.audit import audit
from services.lifecycle_pricing import assert_renew_allowed, resolve_renew_quote, resolve_upgrade_quote
from services.pricing import apply_discount_with_floor, assert_promotions_allowed, resolve_service_order
from services.scheduler_outbox import (
    cancel_auto_renew,
    cancel_service_expire,
    schedule_provision_poll,
    schedule_service_expire,
)
from services.step_up import request_email_challenge, verify_step_up
from utils.pagination import PageParams, page_params, paginate

router = APIRouter()


@router.get(
    "/services",
    response_model=Page[Order],
    summary="My services",
    dependencies=[Depends(require_perm("user.services.read"))],
)
async def my_services(
    pp: PageParams = Depends(page_params),
    q: str | None = Query(
        default=None,
        max_length=128,
        description="Search by service name, order ID, or issued content",
    ),
    acc: UserModel = Depends(get_current_acc),
    session: AsyncSession = Depends(get_db_session),
) -> Page[Order]:
    """Список выданных пользователю услуг (постранично, с опциональным поиском)."""
    stmt = select(UserServicesModel).where(UserServicesModel.account_id == acc.id)
    search = q.strip() if q else ""
    if search:
        pattern = f"%{search}%"
        conditions = [
            UserServicesModel.service.has(ServiceModel.name.ilike(pattern)),
            cast(UserServicesModel.public_data, Text).ilike(pattern),
            cast(UserServicesModel.order_config, Text).ilike(pattern),
        ]
        if search.isdigit():
            conditions.append(UserServicesModel.id == int(search))
        stmt = stmt.where(or_(*conditions))
    stmt = stmt.order_by(UserServicesModel.id.desc())
    items, total, has_more = await paginate(
        session, stmt, Order.from_model, limit=pp.limit, offset=pp.offset
    )
    return Page(
        items=items, total=total, limit=pp.limit, offset=pp.offset, has_more=has_more
    )


@router.get(
    "/services/{service_id}",
    response_model=Order,
    summary="Get user service by ID",
    dependencies=[Depends(require_perm("user.services.read"))],
)
async def get_user_service_by_id(
    service_id: int,
    acc: UserModel = Depends(get_current_acc),
    usvc_mngr: UserServicesMngr = Depends(get_usersvc_mngr),
) -> Order:
    """Получить данные конкретного заказа/услуги пользователя по ID."""
    usvc = await usvc_mngr.s.scalar(
        select(UserServicesModel).where(
            UserServicesModel.id == service_id,
            UserServicesModel.account_id == acc.id,
        )
    )
    if usvc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "service order not found")
    return Order.from_model(usvc)


@router.post(
    "/services/create",
    response_model=Order,
    status_code=status.HTTP_201_CREATED,
    summary="Buy service from balance",
    description=(
        "Charges the service price from balance and delivers it immediately. "
        "Use `/user/purchases/create` to pay via a provider."
    ),
    dependencies=[
        Depends(require_perm("user.services.create")),
        Depends(rate_limit("services.create", LimitKind.SENSITIVE, require_auth=True)),
    ],
)
async def create_service(
    body: OrderCreate,
    request: Request,
    acc: UserModel = Depends(get_current_acc),
    svc_mngr: ServiceMngr = Depends(get_service_mngr),
    usvc_mngr: UserServicesMngr = Depends(get_usersvc_mngr),
    promo_mngr: PromoCodesMngr = Depends(get_promo_mngr),
    triggers: TriggerDispatcher = Depends(get_dispatcher),
) -> Order:
    service = await svc_mngr.get_active(body.service_id)
    resolved = resolve_service_order(
        service,
        custom_amount=body.custom_amount,
        tier_code=body.tier_code,
        components=body.components,
        form=body.form,
    )
    discount = Decimal("0")
    promo = None
    if body.promocode:
        assert_promotions_allowed(service)
        promo = await promo_mngr.load_valid(body.promocode, acc, service_id=service.id)
        catalog = await promo_mngr.catalog_of(promo)
        if catalog.kind != PromoKind.DISCOUNT:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "promo code is not a discount code",
            )
        discount = promo_mngr.discount_for(catalog, service, base_price=resolved.price)
    usvc = await usvc_mngr.create(
        acc,
        service,
        discount=discount,
        custom_amount=body.custom_amount,
        tier_code=body.tier_code,
        components=body.components,
        form=body.form,
    )
    if usvc.status == UsvcStatus.PROVISIONING:
        if promo is not None:
            await promo_mngr.record_use(promo, acc, usvc.id)
        await usvc_mngr.s.commit()
        await triggers.fire(
            TriggerEvent.SERVICE_PROVISIONING_STARTED,
            {
                "order": {"id": usvc.id, "service_id": service.id, "via": "balance"},
                "user": {"id": acc.id, "login": acc.login},
            },
        )
        return Order.from_model(usvc)
    if usvc.status != UsvcStatus.ACTIVE:
        await usvc_mngr.s.rollback()
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, f"service delivery failed: {usvc.error}"
        )
    if promo is not None:
        await promo_mngr.record_use(promo, acc, usvc.id)
    if usvc.expires_at is not None:
        await schedule_service_expire(usvc_mngr.s, usvc.id, usvc.expires_at)
    await usvc_mngr.s.commit()
    await triggers.fire(
        TriggerEvent.ORDER_CREATED,
        {
            "order": {"id": usvc.id, "service_id": service.id, "via": "balance"},
            "user": {"id": acc.id, "login": acc.login},
        },
    )
    return Order.from_model(usvc)


_CUSTOM_ACTION_RE = re.compile(r"^custom\.[a-z][a-z0-9_]{1,31}$")


def _find_custom_action(service: ServiceModel, action_key: str) -> dict | None:
    raw = (service.settings or {}).get("custom_actions")
    if not isinstance(raw, list):
        return None
    for item in raw:
        if isinstance(item, dict) and item.get("key") == action_key:
            return item
    return None


@router.post(
    "/services/{service_id}/action/challenge",
    summary="Request email verification code for custom service action",
    dependencies=[
        Depends(require_perm("user.services.create")),
        Depends(rate_limit("services.action.challenge", LimitKind.SENSITIVE, require_auth=True)),
    ],
)
async def user_service_action_challenge(
    service_id: int,
    body: OrderActionChallengeRequest,
    acc: UserModel = Depends(get_current_acc),
    usvc_mngr: UserServicesMngr = Depends(get_usersvc_mngr),
    svc_mngr: ServiceMngr = Depends(get_service_mngr),
    vk: valkey.Valkey = Depends(get_valkey_client),
    mail: EmailSender = Depends(get_email_sender),
) -> dict:
    usvc = await usvc_mngr.s.scalar(
        select(UserServicesModel).where(
            UserServicesModel.id == service_id,
            UserServicesModel.account_id == acc.id,
        )
    )
    if usvc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "service order not found")
    service = await svc_mngr.s.get(ServiceModel, usvc.service_id)
    if service is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "catalog service not found")
    ca_def = _find_custom_action(service, body.action)
    if ca_def is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"custom action '{body.action}' is not allowed")
    verify_mode = ca_def.get("verify", CustomActionVerify.NONE)
    if verify_mode not in (CustomActionVerify.EMAIL, CustomActionVerify.TWOFA_OR_EMAIL):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "email verification is not applicable for this action",
        )
    ttl = await request_email_challenge(vk, mail, acc, usvc.id, body.action)
    return {"sent": True, "ttl": ttl}


@router.post(
    "/services/{service_id}/action",
    response_model=Order,
    summary="Execute action on user service",
    description="Performs lifecycle action: stop, start, freeze, unfreeze, delete, or custom.<action>.",
    dependencies=[
        Depends(require_perm("user.services.create")),
        Depends(rate_limit("services.action", LimitKind.SENSITIVE, require_auth=True)),
    ],
)
async def user_service_action(
    service_id: int,
    body: OrderActionRequest,
    request: Request,
    acc: UserModel = Depends(get_current_acc),
    usvc_mngr: UserServicesMngr = Depends(get_usersvc_mngr),
    svc_mngr: ServiceMngr = Depends(get_service_mngr),
    vk: valkey.Valkey = Depends(get_valkey_client),
    mail: EmailSender = Depends(get_email_sender),
    triggers: TriggerDispatcher = Depends(get_dispatcher),
) -> Order:
    usvc = await usvc_mngr.s.scalar(
        select(UserServicesModel)
        .where(
            UserServicesModel.id == service_id,
            UserServicesModel.account_id == acc.id,
        )
        .with_for_update()
    )
    if usvc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "service order not found")
    service = await svc_mngr.s.get(ServiceModel, usvc.service_id)
    if service is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "catalog service not found")
    if usvc.status == UsvcStatus.PROVISIONING:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "service is currently provisioning",
        )

    action_norm = body.action.strip().lower()
    if action_norm == ServiceAction.RENEW:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "action is not allowed; renew requires a new paid order or /renew endpoint",
        )

    if action_norm.startswith("custom."):
        if not _CUSTOM_ACTION_RE.match(action_norm):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"invalid custom action '{action_norm}'")
        ca_def = _find_custom_action(service, action_norm)
        if ca_def is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"action '{action_norm}' is not allowed")
        allowed_statuses = ca_def.get("allowed_statuses") or [UsvcStatus.ACTIVE]
        if usvc.status not in allowed_statuses:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"action '{action_norm}' is not available in status '{usvc.status}'",
            )
        verify_mode = str(ca_def.get("verify") or CustomActionVerify.NONE)
        if verify_mode != CustomActionVerify.NONE:
            cfg = request.app.state.settings
            await verify_step_up(
                vk,
                make_secbox(cfg),
                acc,
                usvc.id,
                action_norm,
                verify_mode,
                body.verify_code,
                email_configured=mail.configured,
            )

        usvc = await usvc_mngr.run_action(usvc, service, acc, action_norm)
        if usvc.status == UsvcStatus.PROVISIONING:
            poll_cfg = (usvc.private_data or {}).get("_provisioning") or {}
            interval = int(poll_cfg.get("interval_sec") or 15)
            from datetime import timedelta
            from utils.datetime_utils import utc_now

            await schedule_provision_poll(
                usvc_mngr.s, usvc.id, utc_now() + timedelta(seconds=interval)
            )
        await audit(
            usvc_mngr.s,
            action="service.custom_action",
            actor_id=acc.id,
            target_type="user_service",
            target_id=str(usvc.id),
            meta={"service_id": service.id, "action_key": action_norm},
        )
        await usvc_mngr.s.commit()
        await triggers.fire(
            TriggerEvent.SERVICE_CUSTOM_ACTION,
            {
                "order": {"id": usvc.id, "service_id": service.id},
                "action_key": action_norm,
                "user": {"id": acc.id, "login": acc.login},
            },
        )
        return Order.from_model(usvc)

    allowed = {
        ServiceAction.STOP,
        ServiceAction.START,
        ServiceAction.FREEZE,
        ServiceAction.UNFREEZE,
        ServiceAction.DELETE,
    }
    if action_norm not in allowed:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"action '{action_norm}' is not allowed",
        )
    usvc = await usvc_mngr.run_action(usvc, service, acc, action_norm)
    # Развод stop и freeze: stop управляет только питанием/состоянием без отмены срока,
    # а freeze/delete приостанавливают/завершают биллинговый таймер.
    if action_norm in (ServiceAction.FREEZE, ServiceAction.DELETE):
        await cancel_service_expire(usvc_mngr.s, usvc.id)
        await cancel_auto_renew(usvc_mngr.s, usvc.id)
    elif action_norm == ServiceAction.UNFREEZE and usvc.expires_at is not None:
        await schedule_service_expire(usvc_mngr.s, usvc.id, usvc.expires_at)
        await usvc_mngr.schedule_auto_renew_if_enabled(usvc, service)
    await usvc_mngr.s.commit()
    return Order.from_model(usvc)


@router.post(
    "/services/{service_id}/renew",
    response_model=Order,
    summary="Renew existing user service from balance",
    dependencies=[
        Depends(require_perm("user.services.create")),
        Depends(rate_limit("services.renew", LimitKind.SENSITIVE, require_auth=True)),
    ],
)
async def renew_user_service(
    service_id: int,
    body: OrderRenewRequest,
    acc: UserModel = Depends(get_current_acc),
    usvc_mngr: UserServicesMngr = Depends(get_usersvc_mngr),
    svc_mngr: ServiceMngr = Depends(get_service_mngr),
    promo_mngr: PromoCodesMngr = Depends(get_promo_mngr),
    triggers: TriggerDispatcher = Depends(get_dispatcher),
) -> Order:
    # Строгий порядок блокировок: сначала аккаунт, затем услуга.
    await lock_account(usvc_mngr.s, acc.id)
    usvc = await usvc_mngr.s.scalar(
        select(UserServicesModel)
        .where(
            UserServicesModel.id == service_id,
            UserServicesModel.account_id == acc.id,
        )
        .with_for_update()
    )
    if usvc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "service order not found")
    service = await svc_mngr.s.get(ServiceModel, usvc.service_id)
    if service is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "catalog service not found")

    quote = resolve_renew_quote(
        usvc,
        service,
        tier_code=body.tier_code,
        components=body.components,
    )
    assert_renew_allowed(usvc, service, duration_sec=quote.duration)

    discount = Decimal("0")
    promo = None
    if body.promocode:
        assert_promotions_allowed(service)
        promo = await promo_mngr.load_valid(body.promocode, acc, service_id=service.id)
        catalog = await promo_mngr.catalog_of(promo)
        if catalog.kind != PromoKind.DISCOUNT:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "promo code is not a discount code",
            )
        discount = promo_mngr.discount_for(catalog, service, base_price=quote.price)

    target_config = (
        {**quote.resolved.order_config, "settings": quote.resolved.effective_settings}
        if quote.config_changed
        else None
    )
    if target_config is not None and usvc.pending_order_config is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "another configuration change is already scheduled for the next period",
        )

    final_price = apply_discount_with_floor(service, quote.resolved, discount)
    settings = dict(service.settings or {})
    allow_bonus = bool(settings.get("allow_promotions", True))
    full_bonus_only = bool(settings.get("full_bonus_only", False))
    UserServicesMngr._charge(
        acc,
        final_price,
        allow_bonus=allow_bonus,
        full_bonus_only=full_bonus_only,
    )

    await usvc_mngr.apply_renew(
        usvc,
        service,
        acc,
        duration=quote.duration,
        target_config=target_config,
    )
    if promo is not None:
        await promo_mngr.record_use(promo, acc, usvc.id)
    await audit(
        usvc_mngr.s,
        action="service.renew",
        actor_id=acc.id,
        target_type="user_service",
        target_id=str(usvc.id),
        meta={
            "service_id": service.id,
            "price": str(final_price),
            "duration": quote.duration,
            "config_changed": quote.config_changed,
        },
    )
    await usvc_mngr.s.commit()
    if target_config is not None and usvc.pending_apply_at is not None:
        await triggers.fire(
            TriggerEvent.SERVICE_CONFIG_SCHEDULED,
            {
                "order": {"id": usvc.id, "service_id": service.id},
                "apply_at": usvc.pending_apply_at.isoformat(),
                "user": {"id": acc.id, "login": acc.login},
            },
        )
    return Order.from_model(usvc)


@router.post(
    "/services/{service_id}/upgrade",
    response_model=Order,
    summary="Instant upgrade of an active user service from balance",
    dependencies=[
        Depends(require_perm("user.services.create")),
        Depends(rate_limit("services.upgrade", LimitKind.SENSITIVE, require_auth=True)),
    ],
)
async def upgrade_user_service(
    service_id: int,
    body: OrderUpgradeRequest,
    acc: UserModel = Depends(get_current_acc),
    usvc_mngr: UserServicesMngr = Depends(get_usersvc_mngr),
    svc_mngr: ServiceMngr = Depends(get_service_mngr),
    promo_mngr: PromoCodesMngr = Depends(get_promo_mngr),
) -> Order:
    await lock_account(usvc_mngr.s, acc.id)
    usvc = await usvc_mngr.s.scalar(
        select(UserServicesModel)
        .where(
            UserServicesModel.id == service_id,
            UserServicesModel.account_id == acc.id,
        )
        .with_for_update()
    )
    if usvc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "service order not found")
    service = await svc_mngr.s.get(ServiceModel, usvc.service_id)
    if service is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "catalog service not found")

    quote = resolve_upgrade_quote(
        usvc,
        service,
        tier_code=body.tier_code,
        components=body.components,
    )
    discount = Decimal("0")
    promo = None
    if body.promocode:
        assert_promotions_allowed(service)
        promo = await promo_mngr.load_valid(body.promocode, acc, service_id=service.id)
        catalog = await promo_mngr.catalog_of(promo)
        if catalog.kind != PromoKind.DISCOUNT:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "promo code is not a discount code")
        discount = promo_mngr.discount_for(catalog, service, base_price=quote.delta_price)

    charge_amt = max(Decimal("0.00"), quote.delta_price - discount)
    settings = dict(service.settings or {})
    UserServicesMngr._charge(
        acc,
        charge_amt,
        allow_bonus=bool(settings.get("allow_promotions", True)),
        full_bonus_only=bool(settings.get("full_bonus_only", False)),
    )

    new_cfg = {**quote.resolved.order_config, "settings": quote.resolved.effective_settings}
    await usvc_mngr.apply_upgrade(
        usvc, service, acc, new_config=new_cfg, new_price=quote.new_price
    )
    if promo is not None:
        await promo_mngr.record_use(promo, acc, usvc.id)
    await audit(
        usvc_mngr.s,
        action="service.upgrade",
        actor_id=acc.id,
        target_type="user_service",
        target_id=str(usvc.id),
        meta={"service_id": service.id, "delta_price": str(charge_amt), "new_price": str(quote.new_price)},
    )
    await usvc_mngr.s.commit()
    return Order.from_model(usvc)


@router.patch(
    "/services/{service_id}/auto-renew",
    response_model=Order,
    summary="Enable or disable auto-renewal from balance",
    dependencies=[
        Depends(require_perm("user.services.create")),
        Depends(rate_limit("services.autorenew", LimitKind.SENSITIVE, require_auth=True)),
    ],
)
async def toggle_user_service_auto_renew(
    service_id: int,
    body: OrderAutoRenewRequest,
    acc: UserModel = Depends(get_current_acc),
    usvc_mngr: UserServicesMngr = Depends(get_usersvc_mngr),
    svc_mngr: ServiceMngr = Depends(get_service_mngr),
) -> Order:
    usvc = await usvc_mngr.s.scalar(
        select(UserServicesModel)
        .where(
            UserServicesModel.id == service_id,
            UserServicesModel.account_id == acc.id,
        )
        .with_for_update()
    )
    if usvc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "service order not found")
    service = await svc_mngr.s.get(ServiceModel, usvc.service_id)
    if service is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "catalog service not found")

    if body.enabled:
        settings = dict(service.settings or {})
        if not settings.get("allow_auto_renew", False):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "auto-renewal is not enabled for this service",
            )
        if usvc.status not in (UsvcStatus.ACTIVE, UsvcStatus.STOPPED, UsvcStatus.FROZEN):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"auto-renewal cannot be enabled in status '{usvc.status}'",
            )
        usvc.auto_renew = True
        usvc.auto_renew_attempts = 0
        usvc.auto_renew_last_error = None
        await usvc_mngr.schedule_auto_renew_if_enabled(usvc, service)
    else:
        usvc.auto_renew = False
        await cancel_auto_renew(usvc_mngr.s, usvc.id)

    await usvc_mngr.s.commit()
    return Order.from_model(usvc)


__all__ = ["router"]
