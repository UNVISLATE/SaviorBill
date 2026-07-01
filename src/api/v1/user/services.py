"""Выданные услуги текущего пользователя (/api/v1/user/services)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.auth import get_current_acc
from dependencies.catalog import ServiceMngr, get_service_mngr
from dependencies.db import get_db_session
from dependencies.usersvc import UserServicesMngr, get_usersvc_mngr
from enums import OrderStatus
from models.user import UserModel
from models.user_services import UserServicesModel
from schemas.orders import OrderCreate, Order

router = APIRouter()


@router.get("/services", response_model=list[Order], summary="Мои услуги")
async def my_services(
    acc: UserModel = Depends(get_current_acc),
    session: AsyncSession = Depends(get_db_session),
) -> list[Order]:
    """Список выданных пользователю услуг."""
    rows = await session.scalars(
        select(UserServicesModel)
        .where(UserServicesModel.account_id == acc.id)
        .order_by(UserServicesModel.id.desc())
    )
    return [Order.from_model(s) for s in rows]


@router.post(
    "/services/create",
    response_model=Order,
    status_code=status.HTTP_201_CREATED,
    summary="Заказать услугу с баланса",
    description=(
        "Списывает стоимость услуги с баланса (сначала бонусы) и сразу её "
        "выдаёт. Для оплаты через платёжку используйте /user/purchases/create."
    ),
)
async def create_service(
    body: OrderCreate,
    request: Request,
    acc: UserModel = Depends(get_current_acc),
    svc_mngr: ServiceMngr = Depends(get_service_mngr),
    usvc_mngr: UserServicesMngr = Depends(get_usersvc_mngr),
) -> Order:
    service = await svc_mngr.get_active(body.service_id)
    usvc = await usvc_mngr.create(acc, service, params=body.params)
    if usvc.status != OrderStatus.DELIVERED:
        await usvc_mngr.s.rollback()
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, f"не удалось выдать услугу: {usvc.error}"
        )
    await usvc_mngr.s.commit()
    # Запланировать истечение (если срочная услуга) — планировщик подхватит и сам.
    loop = getattr(request.app.state, "billing_loop", None)
    if loop is not None and usvc.expires_at is not None:
        await loop.enqueue_service(usvc.id, usvc.expires_at)
    return Order.from_model(usvc)


__all__ = ["router"]
