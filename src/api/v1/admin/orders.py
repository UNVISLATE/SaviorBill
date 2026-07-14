"""Админ: выданные услуги/заказы пользователей (/api/v1/admin/orders)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.catalog import ServiceMngr, get_service_mngr
from dependencies.db import get_db_session
from dependencies.rbac import require_perm
from dependencies.triggers import get_dispatcher
from dependencies.usersvc import UserServicesMngr, get_usersvc_mngr
from integrations.triggers import TriggerDispatcher, TriggerEvent
from models.user import UserModel
from models.user_services import UserServicesModel
from schemas.orders import OrderAdmin, OrderGrant
from schemas.page import Page
from utils.pagination import PageParams, page_params, paginate

router = APIRouter()


@router.get(
    "",
    response_model=Page[OrderAdmin],
    dependencies=[Depends(require_perm("orders.read"))],
    summary="Orders",
)
async def list_orders(
    pp: PageParams = Depends(page_params),
    session: AsyncSession = Depends(get_db_session),
) -> Page[OrderAdmin]:
    stmt = select(UserServicesModel).order_by(UserServicesModel.id.desc())
    items, total, has_more = await paginate(
        session, stmt, OrderAdmin.from_model, limit=pp.limit, offset=pp.offset
    )
    return Page(
        items=items, total=total, limit=pp.limit, offset=pp.offset, has_more=has_more
    )


@router.get(
    "/{order_id}",
    response_model=OrderAdmin,
    dependencies=[Depends(require_perm("orders.read"))],
    summary="Order details",
)
async def get_order(
    order_id: int, session: AsyncSession = Depends(get_db_session)
) -> OrderAdmin:
    usvc = await session.get(UserServicesModel, order_id)
    if usvc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "order not found")
    return OrderAdmin.from_model(usvc)


@router.post(
    "/grant",
    response_model=OrderAdmin,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_perm("orders.create"))],
    summary="Grant service",
    description="Create an order without a payment.",
)
async def grant(
    body: OrderGrant,
    session: AsyncSession = Depends(get_db_session),
    svc_mngr: ServiceMngr = Depends(get_service_mngr),
    usvc_mngr: UserServicesMngr = Depends(get_usersvc_mngr),
    triggers: TriggerDispatcher = Depends(get_dispatcher),
) -> OrderAdmin:
    acc = await session.get(UserModel, body.account_id)
    if acc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")
    service = await svc_mngr.get_active(body.service_id)
    usvc = await usvc_mngr.create(acc, service, params=body.params, charge=body.charge)
    await usvc_mngr.s.commit()
    await triggers.fire(
        TriggerEvent.ORDER_CREATED,
        {
            "order": {"id": usvc.id, "service_id": service.id, "via": "admin_grant"},
            "user": {"id": acc.id, "login": acc.login},
        },
    )
    return OrderAdmin.from_model(usvc)


__all__ = ["router"]
