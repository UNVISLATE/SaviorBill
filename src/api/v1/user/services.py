"""Выданные услуги текущего пользователя (/api/v1/user/services)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.auth import get_current_acc
from dependencies.catalog import ServiceMngr, get_service_mngr
from dependencies.db import get_db_session
from dependencies.usersvc import UserSvcMngr, get_usersvc_mngr
from enums import OrderStatus
from models.user import Account
from models.user_svc import UserSvc
from schemas.orders import OrderCreate, OrderOut

router = APIRouter()


@router.get("/services", response_model=list[OrderOut], summary="Мои услуги")
async def my_services(
    acc: Account = Depends(get_current_acc),
    session: AsyncSession = Depends(get_db_session),
) -> list[UserSvc]:
    """Список выданных пользователю услуг."""
    rows = await session.scalars(
        select(UserSvc).where(UserSvc.account_id == acc.id).order_by(UserSvc.id.desc())
    )
    return list(rows)


@router.post(
    "/services/create",
    response_model=OrderOut,
    status_code=status.HTTP_201_CREATED,
    summary="Заказать услугу с баланса",
    description=(
        "Списывает стоимость услуги с баланса (сначала бонусы) и сразу её "
        "выдаёт. Для оплаты через платёжку используйте /user/purchases/create."
    ),
)
async def create_service(
    body: OrderCreate,
    acc: Account = Depends(get_current_acc),
    svc_mngr: ServiceMngr = Depends(get_service_mngr),
    usvc_mngr: UserSvcMngr = Depends(get_usersvc_mngr),
) -> UserSvc:
    service = await svc_mngr.get_active(body.service_id)
    usvc = await usvc_mngr.create(acc, service, params=body.params)
    if usvc.status != OrderStatus.DELIVERED:
        await usvc_mngr.s.rollback()
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, f"не удалось выдать услугу: {usvc.error}"
        )
    await usvc_mngr.s.commit()
    return usvc


__all__ = ["router"]
