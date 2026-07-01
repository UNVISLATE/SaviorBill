"""Промокоды (PromoCodesModel) + менеджер (PromoCodesMngr)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Select,
    String,
    func,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from enums import DiscountType, PromoKind
from models import Base
from models.promo_catalogs import PromoCatalogsModel
from utils.datetime_utils import utc_now


class PromoCodesModel(Base):
    """Промокод — набор символов с лимитом активаций и сроком.

    Что код делает — описывает каталог (``catalog_id``, обязателен). Сам код
    хранит лишь: ``max_uses`` (``None`` — безлимит), ``valid_to`` (``None`` —
    бессрочно) и счётчик активаций.
    """

    __tablename__ = "promocodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        server_default=func.now(),
        nullable=False,
    )

    code: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    catalog_id: Mapped[int] = mapped_column(
        ForeignKey("promo_catalogs.id", ondelete="CASCADE"), index=True, nullable=False
    )

    max_uses: Mapped[int | None] = mapped_column(Integer, nullable=True)
    used_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    valid_to: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class PromoCodesMngr:
    """Операции с промокодами (поведение берётся из каталога)."""

    def __init__(self, session: AsyncSession) -> None:
        self.s = session

    async def list_for(self, catalog_id: int) -> list[PromoCodesModel]:
        """Коды конкретного каталога.

        :arg catalog_id: идентификатор каталога.
        :return: список промокодов каталога.
        """
        rows = await self.s.scalars(self.stmt_for(catalog_id))
        return list(rows)

    def stmt_for(self, catalog_id: int) -> Select:
        """Базовый select кодов каталога (для пагинации).

        :arg catalog_id: идентификатор каталога.
        :return: select без limit/offset.
        """
        return (
            select(PromoCodesModel)
            .where(PromoCodesModel.catalog_id == catalog_id)
            .order_by(PromoCodesModel.id)
        )

    async def create_batch(
        self,
        catalog_id: int,
        *,
        codes: list[str] | None = None,
        count: int = 0,
        prefix: str = "",
        max_uses: int | None = None,
        valid_to: datetime | None = None,
    ) -> list[PromoCodesModel]:
        """Создать пачку кодов в каталоге (каталог обязателен).

        :arg catalog_id: каталог, описывающий действие кодов.
        :arg codes: явные коды; если не заданы — генерируются ``count`` штук.
        :arg count: сколько случайных кодов выпустить при отсутствии ``codes``.
        :arg prefix: префикс для генерируемых кодов.
        :arg max_uses: лимит активаций (``None`` — безлимит).
        :arg valid_to: срок действия (``None`` — бессрочно).
        :return: созданные промокоды.
        """
        catalog = await self.s.get(PromoCatalogsModel, catalog_id)
        if catalog is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "каталог не найден")

        values = list(codes) if codes else [self._gen(prefix) for _ in range(count)]
        created: list[PromoCodesModel] = []
        for value in values:
            promo = PromoCodesModel(
                code=value,
                catalog_id=catalog_id,
                max_uses=max_uses,
                valid_to=valid_to,
            )
            self.s.add(promo)
            created.append(promo)
        await self.s.flush()
        return created

    @staticmethod
    def _gen(prefix: str = "") -> str:
        """Сгенерировать случайный код.

        :arg prefix: префикс кода.
        :return: строка вида ``PREFIXXXXXXXXXX``.
        """
        import secrets

        body = secrets.token_urlsafe(9).replace("-", "").replace("_", "").upper()
        return f"{prefix}{body}"[:64]

    async def load_valid(self, code: str, acc) -> PromoCodesModel:
        """Найти код и проверить активность, срок и лимиты (общий + per-user).

        :arg code: символы промокода.
        :arg acc: аккаунт, активирующий код.
        :return: валидный промокод.
        """
        from models.promo_use import PromoUseModel

        promo = await self.s.scalar(
            select(PromoCodesModel).where(PromoCodesModel.code == code)
        )
        if promo is None or not promo.is_active:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "промокод недействителен")

        now = utc_now()
        if promo.valid_to and now > promo.valid_to:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "срок промокода истёк")
        if promo.max_uses is not None and promo.used_count >= promo.max_uses:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "лимит использований исчерпан"
            )

        catalog = await self.catalog_of(promo)
        used_by_user = await self.s.scalar(
            select(func.count())
            .select_from(PromoUseModel)
            .where(
                PromoUseModel.promocode_id == promo.id,
                PromoUseModel.account_id == acc.id,
            )
        )
        if used_by_user >= catalog.per_user:
            raise HTTPException(status.HTTP_409_CONFLICT, "промокод уже использован")
        return promo

    async def catalog_of(self, promo: PromoCodesModel) -> PromoCatalogsModel:
        """Каталог, описывающий действие промокода.

        :arg promo: промокод.
        :return: активный каталог промокода.
        """
        catalog = await self.s.get(PromoCatalogsModel, promo.catalog_id)
        if catalog is None or not catalog.is_active:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "каталог промокода недоступен"
            )
        return catalog

    async def record_use(
        self, promo: PromoCodesModel, acc, order_id: int | None = None
    ) -> None:
        """Зафиксировать активацию и увеличить счётчик.

        :arg promo: активированный код.
        :arg acc: аккаунт пользователя.
        :arg order_id: связанный заказ (если есть).
        """
        from models.promo_use import PromoUseModel

        self.s.add(
            PromoUseModel(promocode_id=promo.id, account_id=acc.id, order_id=order_id)
        )
        promo.used_count += 1
        await self.s.flush()

    def discount_for(self, catalog: PromoCatalogsModel, service) -> Decimal:
        """Рассчитать скидку каталога для услуги.

        :arg catalog: каталог промокода (kind=discount).
        :arg service: услуга, к которой применяется скидка.
        :return: размер скидки (не больше цены услуги).
        """
        if catalog.kind != PromoKind.DISCOUNT:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "промокод не является скидочным"
            )
        if catalog.discount_type == DiscountType.PERCENT:
            disc = (service.price * catalog.value / Decimal("100")).quantize(
                Decimal("0.01")
            )
        else:
            disc = catalog.value
        return max(Decimal("0"), min(disc, service.price))

    async def apply_bonus(self, catalog: PromoCatalogsModel, acc) -> Decimal:
        """Зачислить бонус на бонусный баланс.

        :arg catalog: каталог промокода (kind=bonus).
        :arg acc: аккаунт пользователя.
        :return: сумма зачисленного бонуса.
        """
        if catalog.kind != PromoKind.BONUS:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "промокод не бонусный")
        acc.bonus_balance += catalog.value
        await self.s.flush()
        return catalog.value


__all__ = ["PromoCodesModel", "PromoCodesMngr"]
