"""Платежи текущего пользователя (/api/v1/user/purchases)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.auth import get_current_acc
from dependencies.catalog import ServiceMngr, get_service_mngr
from dependencies.db import get_db_session
from dependencies.payment import (
    PayMngr,
    PaymentProvidersMngr,
    get_pay_mngr,
    get_pay_providers_mngr,
)
from dependencies.rbac import require_perm
from dependencies.ratelimit import LimitKind, rate_limit
from dependencies.triggers import get_dispatcher
from dependencies.usersvc import UserServicesMngr, get_usersvc_mngr
from enums import PayTarget
from integrations.triggers import TriggerDispatcher, TriggerEvent
from models.user import UserModel
from models.user_payments import UserPaymentsModel
from schemas.page import Page
from schemas.payment_provider import PayProviderPublic
from schemas.payments import PaymentCreate, Payment
from utils.apidoc import with_fields
from utils.pagination import PageParams, page_params, paginate

router = APIRouter()


@router.get(
    "/purchases/providers",
    response_model=list[PayProviderPublic],
    summary="Доступные платёжные провайдеры",
    description=(
        "Список включённых платёжных провайдеров для выбора при создании "
        "платежа. Требует аутентификации (Bearer)."
    ),
    dependencies=[Depends(require_perm("user.purchases.read"))],
)
async def list_pay_providers(
    acc: UserModel = Depends(get_current_acc),
    mngr: PaymentProvidersMngr = Depends(get_pay_providers_mngr),
) -> list[PayProviderPublic]:
    """Включённые провайдеры (без секретов и служебных полей)."""
    rows = await mngr.list_enabled()
    return [PayProviderPublic.from_model(p) for p in rows]


@router.get(
    "/purchases",
    response_model=Page[Payment],
    summary="Мои платежи",
    dependencies=[Depends(require_perm("user.purchases.read"))],
)
async def my_purchases(
    pp: PageParams = Depends(page_params),
    acc: UserModel = Depends(get_current_acc),
    session: AsyncSession = Depends(get_db_session),
) -> Page[Payment]:
    """Список платежей текущего пользователя (постранично)."""
    stmt = (
        select(UserPaymentsModel)
        .where(UserPaymentsModel.account_id == acc.id)
        .order_by(UserPaymentsModel.id.desc())
    )
    items, total, has_more = await paginate(
        session, stmt, Payment.from_model, limit=pp.limit, offset=pp.offset
    )
    return Page(
        items=items, total=total, limit=pp.limit, offset=pp.offset, has_more=has_more
    )


@router.post(
    "/purchases/create",
    response_model=Payment,
    status_code=status.HTTP_201_CREATED,
    summary="Создать платёж",
    description=with_fields(
        "Инициализирует платёж через провайдера. В `public_data` ответа "
        "обычно лежит ссылка для редиректа на оплату. При `target=service` "
        "услуга будет выдана автоматически по успешному колбэку (тогда "
        "обязателен `service_id`).",
        PaymentCreate,
    ),
    dependencies=[
        Depends(require_perm("user.purchases.create")),
        Depends(rate_limit("purchases.create", LimitKind.SENSITIVE)),
    ],
)
async def create_purchase(
    body: PaymentCreate,
    acc: UserModel = Depends(get_current_acc),
    pay_mngr: PayMngr = Depends(get_pay_mngr),
    svc_mngr: ServiceMngr = Depends(get_service_mngr),
    usvc_mngr: UserServicesMngr = Depends(get_usersvc_mngr),
    triggers: TriggerDispatcher = Depends(get_dispatcher),
) -> Payment:
    user_svc_id: int | None = None

    if body.target == PayTarget.SERVICE:
        if not body.service_id:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "для target=service нужен service_id"
            )
        service = await svc_mngr.get_active(body.service_id)
        # Создаём отложенную выдачу (без списания/доставки — доставит колбэк).
        usvc = await usvc_mngr.create(acc, service, charge=False, deliver=False)
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
    if body.target == PayTarget.SERVICE:
        await triggers.fire(
            TriggerEvent.ORDER_CREATED,
            {
                "order": {
                    "id": user_svc_id,
                    "service_id": body.service_id,
                    "via": "payment",
                },
                "user": {"id": acc.id, "login": acc.login},
            },
        )
    return Payment.from_model(payment)


__all__ = ["router"]
