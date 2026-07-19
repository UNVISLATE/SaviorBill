"""Платежи текущего пользователя (/api/v1/user/purchases)."""

from __future__ import annotations

from decimal import Decimal

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
from dependencies.promo import PromoCodesMngr, get_promo_mngr
from dependencies.rbac import require_perm
from dependencies.ratelimit import LimitKind, rate_limit
from dependencies.triggers import get_dispatcher
from dependencies.usersvc import UserServicesMngr, get_usersvc_mngr
from enums import PayTarget, PromoKind
from lifecycle.triggers import TriggerDispatcher, TriggerEvent
from models.user import UserModel
from models.user_payments import UserPaymentsModel
from schemas.page import Page
from schemas.payment_provider import PayProviderPublic
from schemas.payments import PaymentCreate, Payment
from utils.pagination import PageParams, page_params, paginate

router = APIRouter()


@router.get(
    "/purchases/providers",
    response_model=list[PayProviderPublic],
    summary="Available payment providers",
    description="Enabled providers available for creating a payment.",
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
    summary="My payments",
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
    summary="Create payment",
    description=(
        "Creates a payment. For `target=service`, `service_id` is required and "
        "the service is delivered after a successful callback."
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
    promo_mngr: PromoCodesMngr = Depends(get_promo_mngr),
    triggers: TriggerDispatcher = Depends(get_dispatcher),
) -> Payment:
    user_svc_id: int | None = None
    # Авторитетная сумма: для услуги — только server-side service.price
    # (body.amount для target=service запрещён самой схемой); для
    # пополнения баланса — то, что прислал клиент.
    amount = body.amount

    if body.target == PayTarget.SERVICE:
        if not body.service_id:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "service_id is required for target=service"
            )
        service = await svc_mngr.get_active(body.service_id)
        discount = Decimal("0")
        promo_id: int | None = None
        if body.promocode:
            promo = await promo_mngr.load_valid(body.promocode, acc)
            catalog = await promo_mngr.catalog_of(promo)
            if catalog.kind != PromoKind.DISCOUNT:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    "promo code is not a discount code",
                )
            discount = promo_mngr.discount_for(catalog, service)
            promo_id = promo.id
        amount = service.price - discount
        # Создаём отложенную выдачу (без списания/доставки — доставит колбэк).
        usvc = await usvc_mngr.create(
            acc, service, discount=discount, charge=False, deliver=False
        )
        if promo_id is not None:
            # Погашение кода фиксируется только при подтверждённой оплате
            # (см. PayMngr._settle) — здесь только помечаем, каким кодом
            # оплата будет погашена, без записи в promocode_use/used_count.
            usvc.private_data = {**(usvc.private_data or {}), "promocode_id": promo_id}
        user_svc_id = usvc.id

    payment = await pay_mngr.create(
        acc,
        amount,
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
