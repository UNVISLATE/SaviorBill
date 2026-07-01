"""Выданные услуги текущего пользователя (/api/v1/user/services)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.auth import get_current_acc
from dependencies.catalog import ServiceMngr, get_service_mngr
from dependencies.db import get_db_session
from dependencies.ratelimit import LimitKind, rate_limit
from dependencies.usersvc import UserServicesMngr, get_usersvc_mngr
from enums import UsvcStatus
from models.user import UserModel
from models.user_services import UserServicesModel
from schemas.orders import OrderCreate, Order
from schemas.page import Page
from utils.apidoc import with_fields
from utils.pagination import paginate

router = APIRouter()


@router.get("/services", response_model=Page[Order], summary="Мои услуги")
async def my_services(
    limit: int = Query(50, ge=1, le=200, description="Размер страницы (опционально)"),
    offset: int = Query(0, ge=0, description="Смещение выборки (опционально)"),
    acc: UserModel = Depends(get_current_acc),
    session: AsyncSession = Depends(get_db_session),
) -> Page[Order]:
    """Список выданных пользователю услуг (постранично)."""
    stmt = (
        select(UserServicesModel)
        .where(UserServicesModel.account_id == acc.id)
        .order_by(UserServicesModel.id.desc())
    )
    items, total = await paginate(
        session, stmt, Order.from_model, limit=limit, offset=offset
    )
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.post(
    "/services/create",
    response_model=Order,
    status_code=status.HTTP_201_CREATED,
    summary="Заказать услугу с баланса",
    description=with_fields(
        "Списывает стоимость услуги с баланса (сначала бонусы) и сразу её "
        "выдаёт. Для оплаты через платёжку используйте /user/purchases/create.",
        OrderCreate,
    ),
    dependencies=[Depends(rate_limit("services.create", LimitKind.SENSITIVE))],
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
    if usvc.status != UsvcStatus.ACTIVE:
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
