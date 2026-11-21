from __future__ import annotations

"""Выданные услуги текущего пользователя (/api/v1/user/services)."""

import logging

logger = logging.getLogger(__name__)

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import Text, cast, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.auth import get_current_acc
from dependencies.catalog import ServiceMngr, get_service_mngr
from dependencies.db import get_db_session
from dependencies.promo import PromoCodesMngr, get_promo_mngr
from dependencies.rbac import require_perm
from dependencies.ratelimit import LimitKind, rate_limit
from dependencies.triggers import get_dispatcher
from dependencies.usersvc import UserServicesMngr, get_usersvc_mngr
from enums import UsvcStatus, PromoKind, ServiceAction
from lifecycle.triggers import TriggerDispatcher, TriggerEvent
from models.service import ServiceModel
from models.user import UserModel
from models.user_services import UserServicesModel
from schemas.orders import OrderCreate, Order, OrderActionRequest
from schemas.page import Page
from services.pricing import resolve_service_order
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
        if (getattr(service, "settings", {}) or {}).get("allow_promotions", True) is False:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "service does not participate in promotions",
            )
        promo = await promo_mngr.load_valid(body.promocode, acc)
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
    if usvc.status != UsvcStatus.ACTIVE:
        await usvc_mngr.s.rollback()
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, f"service delivery failed: {usvc.error}"
        )
    if promo is not None:
        await promo_mngr.record_use(promo, acc, usvc.id)
    await usvc_mngr.s.commit()
    await triggers.fire(
        TriggerEvent.ORDER_CREATED,
        {
            "order": {"id": usvc.id, "service_id": service.id, "via": "balance"},
            "user": {"id": acc.id, "login": acc.login},
        },
    )
    # Запланировать истечение (если срочная услуга) — планировщик подхватит и сам.
    loop = getattr(request.app.state, "billing_loop", None)
    if loop is not None and usvc.expires_at is not None:
        await loop.enqueue_service(usvc.id, usvc.expires_at)
    return Order.from_model(usvc)


@router.post(
    "/services/{service_id}/action",
    response_model=Order,
    summary="Execute action on user service",
    description="Performs lifecycle action: renew, freeze, stop, resume.",
    dependencies=[
        Depends(require_perm("user.services.create")),
        Depends(rate_limit("services.action", LimitKind.SENSITIVE, require_auth=True)),
    ],
)
async def user_service_action(
    service_id: int,
    body: OrderActionRequest,
    acc: UserModel = Depends(get_current_acc),
    usvc_mngr: UserServicesMngr = Depends(get_usersvc_mngr),
    svc_mngr: ServiceMngr = Depends(get_service_mngr),
) -> Order:
    usvc = await usvc_mngr.s.scalar(
        select(UserServicesModel).where(
            UserServicesModel.id == service_id,
            UserServicesModel.account_id == acc.id,
        )
    )
    if usvc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "service order not found")
    service = await svc_mngr.get(usvc.service_id)
    if service is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "catalog service not found")

    action_norm = body.action.strip().lower()
    allowed = {ServiceAction.STOP, ServiceAction.FREEZE, "start", "unfreeze", ServiceAction.DELETE}
    if action_norm == ServiceAction.RENEW:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "action is not allowed; renew requires a new paid order",
        )
    if action_norm not in allowed:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"action '{action_norm}' is not allowed",
        )
    usvc = await usvc_mngr.run_action(usvc, service, acc, action_norm)
    await usvc_mngr.s.commit()
    return Order.from_model(usvc)


__all__ = ["router"]
