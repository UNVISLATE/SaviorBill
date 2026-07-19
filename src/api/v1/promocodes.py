"""Активация промокодов."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from dependencies.auth import get_current_acc, get_current_acc_optional
from dependencies.catalog import ServiceMngr, get_service_mngr
from dependencies.promo import PromoCodesMngr, get_promo_mngr
from dependencies.ratelimit import LimitKind, rate_limit
from dependencies.triggers import get_dispatcher
from dependencies.usersvc import UserServicesMngr, get_usersvc_mngr
from enums import UsvcStatus, PromoKind
from lifecycle.triggers import TriggerDispatcher, TriggerEvent
from models.user import UserModel
from schemas.promo import PromoRedeem, PromoResult, PromoQuote

router = APIRouter(prefix="/api/v1/promocodes", tags=["promocodes"])


@router.get(
    "/{code}/quote",
    response_model=PromoQuote,
    summary="Preview discount for a service",
    description=(
        "Non-mutating preview of the discount a code would give for a service. "
        "Without authentication, per-user usage limits cannot be checked — "
        "only the code's general validity (active/not expired/kind=discount)."
    ),
)
async def quote(
    code: str,
    service_id: int = Query(description="Service ID to quote the discount for"),
    acc: UserModel | None = Depends(get_current_acc_optional),
    promo_mngr: PromoCodesMngr = Depends(get_promo_mngr),
    svc_mngr: ServiceMngr = Depends(get_service_mngr),
) -> PromoQuote:
    service = await svc_mngr.get_active(service_id)
    valid, discount, reason = await promo_mngr.quote_for(code, service, acc)
    return PromoQuote(
        valid=valid,
        code=code,
        service_id=service_id,
        price=service.price,
        discount=discount,
        final_price=service.price - discount,
        reason=reason,
    )


@router.post(
    "/redeem",
    response_model=PromoResult,
    summary="Redeem promo code",
    description="Redeems `bonus` and `service` promo codes. Use discount codes when ordering a service.",
    dependencies=[Depends(rate_limit("promocodes.redeem", LimitKind.SENSITIVE))],
)
async def redeem(
    body: PromoRedeem,
    acc: UserModel = Depends(get_current_acc),
    promo_mngr: PromoCodesMngr = Depends(get_promo_mngr),
    svc_mngr: ServiceMngr = Depends(get_service_mngr),
    usvc_mngr: UserServicesMngr = Depends(get_usersvc_mngr),
    triggers: TriggerDispatcher = Depends(get_dispatcher),
) -> PromoResult:
    promo = await promo_mngr.load_valid(body.code, acc)
    catalog = await promo_mngr.catalog_of(promo)

    if catalog.kind == PromoKind.BONUS:
        added = await promo_mngr.apply_bonus(catalog, acc)
        await promo_mngr.record_use(promo, acc)
        await promo_mngr.s.commit()
        return PromoResult(kind="bonus", message="bonus credited", bonus_added=added)

    if catalog.kind == PromoKind.SERVICE:
        if not catalog.service_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "catalog service not set")
        service = await svc_mngr.get_active(catalog.service_id)
        order = await usvc_mngr.create(acc, service, discount=service.price)
        if order.status != UsvcStatus.ACTIVE:
            await usvc_mngr.s.rollback()
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY, f"service delivery failed: {order.error}"
            )
        await promo_mngr.record_use(promo, acc, order.id)
        await promo_mngr.s.commit()
        await triggers.fire(
            TriggerEvent.ORDER_CREATED,
            {
                "order": {"id": order.id, "service_id": service.id, "via": "promo"},
                "user": {"id": acc.id, "login": acc.login},
            },
        )
        return PromoResult(
            kind="service", message="service delivered", order_id=order.id
        )

    raise HTTPException(
        status.HTTP_400_BAD_REQUEST,
        "discount promo code must be used when ordering a service",
    )


__all__ = ["router"]
