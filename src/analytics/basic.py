"""Базовый уровень аналитики — простые SQL-агрегаты (без Polars).

Право доступа: ``analytics.basic.read`` (см. IMPLEMENTATION_PLAN §13.1).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from enums import PayStatus, UsvcStatus
from models.promo_codes import PromoCodesModel
from models.promo_use import PromoUseModel
from models.service import ServiceModel
from models.service_keys import ServiceKeysModel
from models.user_payments import UserPaymentsModel
from models.user_services import UserServicesModel

# Статусы выдачи услуги, которые считаются "продажей" (услуга реально была
# доставлена в какой-то момент) — не pending (ещё не доставлена) и не
# failed/cancelled (не состоялась).
_SOLD_STATUSES = (
    UsvcStatus.ACTIVE,
    UsvcStatus.FROZEN,
    UsvcStatus.STOPPED,
    UsvcStatus.EXPIRED,
)


class BasicAnalytics:
    """Простые агрегаты по промокодам/платежам/услугам прямым SQL через ORM."""

    def __init__(self, session: AsyncSession) -> None:
        self.s = session

    # --- промокоды ----------------------------------------------------------
    async def promo_summary(self) -> int:
        """Всего погашений промокодов (строк в ``promo_uses``)."""
        n = await self.s.scalar(select(func.count()).select_from(PromoUseModel))
        return int(n or 0)

    def promo_top_stmt(self) -> Select:
        """Select промокодов, отсортированных по числу погашений (для пагинации)."""
        return select(PromoCodesModel).order_by(PromoCodesModel.used_count.desc())

    @staticmethod
    def promo_code_row(row: PromoCodesModel) -> dict:
        """ORM-строка промокода → словарь для :class:`schemas.analytics.PromoCodeStat`."""
        remaining = (
            None if row.max_uses is None else max(0, row.max_uses - row.used_count)
        )
        return {
            "id": row.id,
            "code": row.code,
            "catalog_id": row.catalog_id,
            "used_count": row.used_count,
            "max_uses": row.max_uses,
            "remaining": remaining,
        }

    # --- платежи --------------------------------------------------------------
    async def payments_summary(
        self, *, since: datetime | None = None, until: datetime | None = None
    ) -> dict:
        """Revenue и разбивка по статусам за период (``[since, until)``, любой опционален)."""
        base = select(UserPaymentsModel)
        if since is not None:
            base = base.where(UserPaymentsModel.created_at >= since)
        if until is not None:
            base = base.where(UserPaymentsModel.created_at < until)

        revenue = await self.s.scalar(
            select(func.coalesce(func.sum(UserPaymentsModel.amount), 0)).select_from(
                base.where(UserPaymentsModel.status == PayStatus.PAID).subquery()
            )
        )
        counts: dict[str, int] = {}
        for st in (PayStatus.PAID, PayStatus.FAILED, PayStatus.REFUNDED, PayStatus.PENDING):
            n = await self.s.scalar(
                select(func.count()).select_from(
                    base.where(UserPaymentsModel.status == st).subquery()
                )
            )
            counts[st] = int(n or 0)

        return {
            "period_from": since,
            "period_to": until,
            "revenue": Decimal(revenue or 0),
            "paid_count": counts[PayStatus.PAID],
            "failed_count": counts[PayStatus.FAILED],
            "refunded_count": counts[PayStatus.REFUNDED],
            "pending_count": counts[PayStatus.PENDING],
        }

    def provider_revenue_stmt(
        self, *, since: datetime | None = None, until: datetime | None = None
    ) -> Select:
        """Select revenue/count по провайдеру (paid-платежи), для пагинации."""
        stmt = (
            select(
                UserPaymentsModel.provider,
                func.coalesce(func.sum(UserPaymentsModel.amount), 0).label("revenue"),
                func.count().label("count"),
            )
            .where(UserPaymentsModel.status == PayStatus.PAID)
            .group_by(UserPaymentsModel.provider)
            .order_by(func.sum(UserPaymentsModel.amount).desc())
        )
        if since is not None:
            stmt = stmt.where(UserPaymentsModel.created_at >= since)
        if until is not None:
            stmt = stmt.where(UserPaymentsModel.created_at < until)
        return stmt

    @staticmethod
    def provider_revenue_row(row) -> dict:
        return {
            "provider": row.provider,
            "revenue": Decimal(row.revenue or 0),
            "count": int(row.count or 0),
        }

    # --- услуги -----------------------------------------------------------
    def service_sales_stmt(self) -> Select:
        """Select услуг с числом продаж, отсортированных по продажам (для пагинации).

        Остаток цифровых ключей (``remaining_keys``) считается отдельным
        запросом на строку (:meth:`remaining_keys_for`) — join с агрегатом по
        ``digi_keys`` внутри одного select усложнил бы пагинацию по продажам
        без реальной выгоды (число услуг обычно небольшое).
        """
        sold = func.count(UserServicesModel.id).label("sold")
        return (
            select(ServiceModel.id, ServiceModel.name, sold)
            .outerjoin(
                UserServicesModel,
                (UserServicesModel.service_id == ServiceModel.id)
                & (UserServicesModel.status.in_(_SOLD_STATUSES)),
            )
            .group_by(ServiceModel.id, ServiceModel.name)
            .order_by(sold.desc())
        )

    async def remaining_keys_for(self, service_id: int) -> int | None:
        """Остаток непроданных цифровых ключей услуги (``None`` — нет ни одного ключа).

        Услуги с key-доставкой имеют строки в ``digi_keys``; услуги с
        lua-доставкой — нет ни одной, поэтому отсутствие строк трактуем как
        "неприменимо", а не как ``0`` (иначе выглядело бы как "нет в наличии").
        """
        total = await self.s.scalar(
            select(func.count())
            .select_from(ServiceKeysModel)
            .where(ServiceKeysModel.service_id == service_id)
        )
        if not total:
            return None
        available = await self.s.scalar(
            select(func.count())
            .select_from(ServiceKeysModel)
            .where(
                ServiceKeysModel.service_id == service_id,
                ServiceKeysModel.is_used.is_(False),
            )
        )
        return int(available or 0)

    @staticmethod
    def service_sales_row(row) -> dict:
        """Строка select → словарь (без ``remaining_keys`` — обогащается отдельно,
        см. :meth:`remaining_keys_for`, т.к. это отдельный запрос на услугу).
        """
        return {
            "service_id": row.id,
            "name": row.name,
            "sold": int(row.sold or 0),
            "remaining_keys": None,
        }


__all__ = ["BasicAnalytics"]
