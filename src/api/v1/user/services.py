"""Выданные услуги текущего пользователя (/api/v1/user/services)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.auth import get_current_acc
from dependencies.catalog import ServiceMngr, get_service_mngr
from dependencies.db import get_db_session
from dependencies.rbac import require_perm
from dependencies.ratelimit import LimitKind, rate_limit
from dependencies.triggers import get_dispatcher
from dependencies.usersvc import UserServicesMngr, get_usersvc_mngr
from enums import UsvcStatus
from integrations.triggers import TriggerDispatcher, TriggerEvent
from models.user import UserModel
from models.user_services import UserServicesModel
from schemas.orders import OrderCreate, Order
from schemas.page import Page
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
    acc: UserModel = Depends(get_current_acc),
    session: AsyncSession = Depends(get_db_session),
) -> Page[Order]:
    """Список выданных пользователю услуг (постранично)."""
    stmt = (
        select(UserServicesModel)
        .where(UserServicesModel.account_id == acc.id)
        .order_by(UserServicesModel.id.desc())
    )
    items, total, has_more = await paginate(
        session, stmt, Order.from_model, limit=pp.limit, offset=pp.offset
    )
    return Page(
        items=items, total=total, limit=pp.limit, offset=pp.offset, has_more=has_more
    )


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
        Depends(rate_limit("services.create", LimitKind.SENSITIVE)),
    ],
)
async def create_service(
    body: OrderCreate,
    request: Request,
    acc: UserModel = Depends(get_current_acc),
    svc_mngr: ServiceMngr = Depends(get_service_mngr),
    usvc_mngr: UserServicesMngr = Depends(get_usersvc_mngr),
    triggers: TriggerDispatcher = Depends(get_dispatcher),
) -> Order:
    service = await svc_mngr.get_active(body.service_id)
    usvc = await usvc_mngr.create(acc, service)
    if usvc.status != UsvcStatus.ACTIVE:
        await usvc_mngr.s.rollback()
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, f"service delivery failed: {usvc.error}"
        )
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


__all__ = ["router"]
