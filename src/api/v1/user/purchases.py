"""Платежи текущего пользователя (/api/v1/user/purchases)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.auth import get_current_acc
from dependencies.catalog import ServiceMngr, get_service_mngr
from dependencies.db import get_db_session
from dependencies.payment import PayMngr, get_pay_mngr
from dependencies.usersvc import UserSvcMngr, get_usersvc_mngr
from enums import PayTarget
from models.payment import Payment
from models.user import Account
from schemas.payments import PaymentCreate, PaymentOut

router = APIRouter()


@router.get("/purchases", response_model=list[PaymentOut], summary="Мои платежи")
async def my_purchases(
    acc: Account = Depends(get_current_acc),
    session: AsyncSession = Depends(get_db_session),
) -> list[Payment]:
    """Список платежей текущего пользователя."""
    rows = await session.scalars(
        select(Payment)
        .where(Payment.account_id == acc.id)
        .order_by(Payment.id.desc())
    )
    return list(rows)


@router.post(
    "/purchases/create",
    response_model=PaymentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Создать платёж",
    description=(
        "Инициализирует платёж через провайдера. В `public_data` ответа "
        "обычно лежит ссылка для редиректа на оплату. При `target=service` "
        "услуга будет выдана автоматически по успешному колбэку."
    ),
)
async def create_purchase(
    body: PaymentCreate,
    acc: Account = Depends(get_current_acc),
    pay_mngr: PayMngr = Depends(get_pay_mngr),
    svc_mngr: ServiceMngr = Depends(get_service_mngr),
    usvc_mngr: UserSvcMngr = Depends(get_usersvc_mngr),
) -> Payment:
    user_svc_id: int | None = None

    if body.target == PayTarget.SERVICE:
        if not body.service_id:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "для target=service нужен service_id"
            )
        service = await svc_mngr.get_active(body.service_id)
        # Создаём отложенную выдачу (без списания/доставки — доставит колбэк).
        usvc = await usvc_mngr.create(
            acc, service, params=body.params, charge=False, deliver=False
        )
        user_svc_id = usvc.id

    payment = await pay_mngr.create(
        acc,
        body.amount,
        body.provider,
        target=body.target,
        user_svc_id=user_svc_id,
        return_url=body.return_url,
    )
    await pay_mngr.s.commit()
    return payment


__all__ = ["router"]
