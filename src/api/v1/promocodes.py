"""Активация промокодов."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from dependencies.auth import get_current_acc
from dependencies.catalog import ServiceMngr, get_service_mngr
from dependencies.promo import PromoCodesMngr, get_promo_mngr
from dependencies.ratelimit import LimitKind, rate_limit
from dependencies.usersvc import UserServicesMngr, get_usersvc_mngr
from enums import OrderStatus, PromoKind
from models.user import UserModel
from schemas.promo import PromoRedeem, PromoResult

router = APIRouter(prefix="/api/v1/promocodes", tags=["promocodes"])


@router.post(
    "/redeem",
    response_model=PromoResult,
    summary="Активировать промокод",
    description=(
        "Действие определяет каталог кода: `bonus` — зачисление на бонусный "
        "баланс; `service` — бесплатная выдача услуги. Скидочный код (`discount`) "
        "так не активируется — его передают в поле `promocode` при заказе услуги."
    ),
    dependencies=[Depends(rate_limit("promocodes.redeem", LimitKind.SENSITIVE))],
)
async def redeem(
    body: PromoRedeem,
    acc: UserModel = Depends(get_current_acc),
    promo_mngr: PromoCodesMngr = Depends(get_promo_mngr),
    svc_mngr: ServiceMngr = Depends(get_service_mngr),
    usvc_mngr: UserServicesMngr = Depends(get_usersvc_mngr),
) -> PromoResult:
    promo = await promo_mngr.load_valid(body.code, acc)
    catalog = await promo_mngr.catalog_of(promo)

    if catalog.kind == PromoKind.BONUS:
        added = await promo_mngr.apply_bonus(catalog, acc)
        await promo_mngr.record_use(promo, acc)
        await promo_mngr.s.commit()
        return PromoResult(kind="bonus", message="бонусы зачислены", bonus_added=added)

    if catalog.kind == PromoKind.SERVICE:
        if not catalog.service_id:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "у каталога не задана услуга"
            )
        service = await svc_mngr.get_active(catalog.service_id)
        order = await usvc_mngr.create(acc, service, discount=service.price)
        if order.status != OrderStatus.DELIVERED:
            await usvc_mngr.s.rollback()
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY, f"не удалось выдать услугу: {order.error}"
            )
        await promo_mngr.record_use(promo, acc, order.id)
        await promo_mngr.s.commit()
        return PromoResult(kind="service", message="услуга выдана", order_id=order.id)

    raise HTTPException(
        status.HTTP_400_BAD_REQUEST,
        "скидочный промокод применяется при заказе услуги (поле promocode)",
    )


__all__ = ["router"]
