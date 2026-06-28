"""Логика промокодов: валидация, бонусы, скидки, учёт использований."""

from __future__ import annotations

from decimal import Decimal

from fastapi import Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.db import get_db_session
from enums import DiscountType, PromoKind
from models.promocode import Promocode
from models.promo_use import PromoUse
from models.service import Service
from models.user import Account
from utils.datetime_utils import utc_now


class PromoSvc:
    """Операции с промокодами (без оркестрации заказа — её делает роут)."""

    def __init__(self, session: AsyncSession) -> None:
        self.s = session

    async def load_valid(self, code: str, acc: Account) -> Promocode:
        """Найти промокод и проверить активность/период/лимиты."""
        promo = await self.s.scalar(select(Promocode).where(Promocode.code == code))
        if promo is None or not promo.is_active:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "промокод недействителен")

        now = utc_now()
        if promo.valid_from and now < promo.valid_from:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "промокод ещё не активен")
        if promo.valid_to and now > promo.valid_to:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "срок промокода истёк")
        if promo.max_uses is not None and promo.used_count >= promo.max_uses:
            raise HTTPException(status.HTTP_409_CONFLICT, "лимит использований исчерпан")

        used_by_user = await self.s.scalar(
            select(func.count())
            .select_from(PromoUse)
            .where(PromoUse.promocode_id == promo.id, PromoUse.account_id == acc.id)
        )
        if used_by_user >= promo.per_user:
            raise HTTPException(status.HTTP_409_CONFLICT, "промокод уже использован")
        return promo

    async def record_use(
        self, promo: Promocode, acc: Account, order_id: int | None = None
    ) -> None:
        """Зафиксировать применение промокода и увеличить счётчик."""
        self.s.add(PromoUse(promocode_id=promo.id, account_id=acc.id, order_id=order_id))
        promo.used_count += 1
        await self.s.flush()

    def discount_for(self, promo: Promocode, service: Service) -> Decimal:
        """Рассчитать скидку промокода для услуги."""
        if promo.kind != PromoKind.DISCOUNT:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "промокод не является скидочным")
        if promo.discount_type == DiscountType.PERCENT:
            disc = (service.price * promo.value / Decimal("100")).quantize(Decimal("0.01"))
        else:
            disc = promo.value
        return max(Decimal("0"), min(disc, service.price))

    async def apply_bonus(self, promo: Promocode, acc: Account) -> Decimal:
        """Зачислить бонус на бонусный баланс."""
        if promo.kind != PromoKind.BONUS:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "промокод не бонусный")
        acc.bonus_balance += promo.value
        await self.s.flush()
        return promo.value


def get_promo_svc(session: AsyncSession = Depends(get_db_session)) -> PromoSvc:
    return PromoSvc(session)


__all__ = ["PromoSvc", "get_promo_svc"]
