"""Начисление реферальных бонусов пригласившему (ReferralMngr)."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.ext.asyncio import AsyncSession

from models.system_settings import SystemSettingsModel
from models.user import UserModel

_CENT = Decimal("0.01")
_HUNDRED = Decimal("100")


class ReferralMngr:
    """Начисляет бонус рефереру за покупку приглашённого пользователя.

    Размер бонуса определяется в порядке приоритета:
      1. ``service.settings.referral_amount`` — фиксированная сумма (переопределяет %);
      2. ``service.settings.referral_percent`` — процент от суммы покупки;
      3. глобальный процент из настройки ``referral.percent``.

    Бонус зачисляется на ``bonus_balance`` реферера.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.s = session

    async def _global_percent(self) -> Decimal:
        row = await self.s.get(SystemSettingsModel, "referral.percent")
        if row is None or not row.value:
            return Decimal("0")
        try:
            return Decimal(str(row.value))
        except (ArithmeticError, ValueError):
            return Decimal("0")

    @staticmethod
    def _from_settings(settings: dict, amount: Decimal) -> Decimal | None:
        """Вычислить бонус по настройкам услуги (или ``None``, если их нет)."""
        raw_amount = settings.get("referral_amount")
        if raw_amount not in (None, ""):
            try:
                return Decimal(str(raw_amount))
            except (ArithmeticError, ValueError):
                return None
        raw_percent = settings.get("referral_percent")
        if raw_percent not in (None, ""):
            try:
                return amount * Decimal(str(raw_percent)) / _HUNDRED
            except (ArithmeticError, ValueError):
                return None
        return None

    async def credit(
        self, buyer: UserModel, service, amount: Decimal
    ) -> Decimal | None:
        """Начислить бонус рефереру за покупку.

        :arg buyer: покупатель (приглашённый пользователь).
        :arg service: эталонная услуга (для per-service переопределения); может
            быть ``None``.
        :arg amount: сумма покупки, от которой считается процент.
        :return: начисленный бонус или ``None``, если начисления не было.
        """
        if buyer is None or buyer.referred_by is None or amount <= 0:
            return None
        if buyer.referred_by == buyer.id:
            return None

        settings = (getattr(service, "settings", None) or {}) if service else {}
        bonus = self._from_settings(settings, amount)
        if bonus is None:
            bonus = amount * (await self._global_percent()) / _HUNDRED

        bonus = bonus.quantize(_CENT, rounding=ROUND_HALF_UP)
        if bonus <= 0:
            return None

        referrer = await self.s.get(UserModel, buyer.referred_by)
        if referrer is None:
            return None
        referrer.bonus_balance += bonus
        await self.s.flush()
        return bonus


__all__ = ["ReferralMngr"]
