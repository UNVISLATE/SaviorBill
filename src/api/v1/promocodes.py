"""Активация промокодов."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from dependencies.auth import get_current_acc
from dependencies.catalog import ServiceMngr, get_service_mngr
from dependencies.promo import PromoSvc, get_promo_svc
from dependencies.usersvc import UserSvcMngr, get_usersvc_mngr
from enums import OrderStatus, PromoKind
from models.user import Account
from schemas.promo import PromoRedeem, PromoResult

router = APIRouter(prefix="/api/v1/promocodes", tags=["promocodes"])


@router.post(
    "/redeem",
    response_model=PromoResult,
    summary="Активировать промокод",
    description=(
        "Поддерживаются типы: `bonus` — зачисление на бонусный баланс; "
        "`service` — бесплатная выдача услуги. Промокод `discount` так не "
        "активируется — его передают в `promocode` при заказе услуги."
    ),
)
async def redeem(
    body: PromoRedeem,
    acc: Account = Depends(get_current_acc),
    promo_svc: PromoSvc = Depends(get_promo_svc),
    svc_mngr: ServiceMngr = Depends(get_service_mngr),
    usvc_mngr: UserSvcMngr = Depends(get_usersvc_mngr),
) -> PromoResult:
    promo = await promo_svc.load_valid(body.code, acc)

    if promo.kind == PromoKind.BONUS:
        added = await promo_svc.apply_bonus(promo, acc)
        await promo_svc.record_use(promo, acc)
        await promo_svc.s.commit()
        return PromoResult(kind="bonus", message="бонусы зачислены", bonus_added=added)

    if promo.kind == PromoKind.SERVICE:
        if not promo.service_id:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "у промокода не задана услуга"
            )
        service = await svc_mngr.get_active(promo.service_id)
        order = await usvc_mngr.create(acc, service, discount=service.price)
        if order.status != OrderStatus.DELIVERED:
            await usvc_mngr.s.rollback()
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY, f"не удалось выдать услугу: {order.error}"
            )
        await promo_svc.record_use(promo, acc, order.id)
        await promo_svc.s.commit()
        return PromoResult(kind="service", message="услуга выдана", order_id=order.id)

    raise HTTPException(
        status.HTTP_400_BAD_REQUEST,
        "скидочный промокод применяется при заказе услуги (поле promocode)",
    )


__all__ = ["router"]
