"""Админ: выданные услуги/заказы пользователей (/api/v1/admin/orders)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.catalog import ServiceMngr, get_service_mngr
from dependencies.db import get_db_session
from dependencies.rbac import require_perm
from dependencies.usersvc import UserSvcMngr, get_usersvc_mngr
from models.user import Account
from models.user_svc import UserSvc
from schemas.orders import OrderAdminOut, OrderGrant

router = APIRouter()


@router.get(
    "/orders",
    response_model=list[OrderAdminOut],
    dependencies=[Depends(require_perm("orders.read"))],
    summary="Список выдач",
)
async def list_orders(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db_session),
) -> list[UserSvc]:
    rows = await session.scalars(
        select(UserSvc).order_by(UserSvc.id.desc()).limit(limit).offset(offset)
    )
    return list(rows)


@router.get(
    "/orders/{order_id}",
    response_model=OrderAdminOut,
    dependencies=[Depends(require_perm("orders.read"))],
    summary="Карточка выдачи",
)
async def get_order(
    order_id: int, session: AsyncSession = Depends(get_db_session)
) -> UserSvc:
    usvc = await session.get(UserSvc, order_id)
    if usvc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "выдача не найдена")
    return usvc


@router.post(
    "/orders/grant",
    response_model=OrderAdminOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_perm("orders.edit"))],
    summary="Выдать услугу вручную",
    description=(
        "Создаёт выдачу без привязки к платежу (`payment_id = NULL`). "
        "По умолчанию без списания с баланса (подарок)."
    ),
)
async def grant(
    body: OrderGrant,
    session: AsyncSession = Depends(get_db_session),
    svc_mngr: ServiceMngr = Depends(get_service_mngr),
    usvc_mngr: UserSvcMngr = Depends(get_usersvc_mngr),
) -> UserSvc:
    acc = await session.get(Account, body.account_id)
    if acc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "пользователь не найден")
    service = await svc_mngr.get_active(body.service_id)
    usvc = await usvc_mngr.create(
        acc, service, params=body.params, charge=body.charge
    )
    await usvc_mngr.s.commit()
    return usvc


__all__ = ["router"]
