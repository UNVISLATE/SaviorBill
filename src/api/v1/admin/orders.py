"""Админ: выданные услуги/заказы пользователей (/api/v1/admin/orders)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.catalog import ServiceMngr, get_service_mngr
from dependencies.db import get_db_session
from dependencies.rbac import require_perm
from dependencies.usersvc import UserServicesMngr, get_usersvc_mngr
from models.user import UserModel
from models.user_services import UserServicesModel
from schemas.orders import OrderAdmin, OrderGrant
from schemas.page import Page
from utils.pagination import PageParams, page_params, paginate
from utils.apidoc import with_fields

router = APIRouter()


@router.get(
    "/orders",
    response_model=Page[OrderAdmin],
    dependencies=[Depends(require_perm("orders.read"))],
    summary="Список выдач",
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
    "/orders/{order_id}",
    response_model=OrderAdmin,
    dependencies=[Depends(require_perm("orders.read"))],
    summary="Карточка выдачи",
)
async def get_order(
    order_id: int, session: AsyncSession = Depends(get_db_session)
) -> OrderAdmin:
    usvc = await session.get(UserServicesModel, order_id)
    if usvc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "выдача не найдена")
    return OrderAdmin.from_model(usvc)


@router.post(
    "/orders/grant",
    response_model=OrderAdmin,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_perm("orders.create"))],
    summary="Выдать услугу вручную",
    description=with_fields(
        (
            "Создаёт выдачу без привязки к платежу (`payment_id = NULL`). "
            "По умолчанию без списания с баланса (подарок)."
        ),
        OrderGrant,
    ),
)
async def grant(
    body: OrderGrant,
    session: AsyncSession = Depends(get_db_session),
    svc_mngr: ServiceMngr = Depends(get_service_mngr),
    usvc_mngr: UserServicesMngr = Depends(get_usersvc_mngr),
) -> OrderAdmin:
    acc = await session.get(UserModel, body.account_id)
    if acc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "пользователь не найден")
    service = await svc_mngr.get_active(body.service_id)
    usvc = await usvc_mngr.create(acc, service, params=body.params, charge=body.charge)
    await usvc_mngr.s.commit()
    return OrderAdmin.from_model(usvc)


__all__ = ["router"]
