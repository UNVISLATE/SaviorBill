"""Базовый класс нативных интеграций выдачи услуг."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from utils.luabus import LuaBus
from security.sec.box import SecBox


class BaseIssuer:
    """Базовый способ выдачи услуги."""

    def __init__(
        self,
        session: AsyncSession,
        bus: LuaBus | None = None,
        box: SecBox | None = None,
    ) -> None:
        self.s = session
        self.bus = bus
        self.box = box

    async def issue(self, usvc, service, acc) -> None:  # noqa: ANN001 — ORM-объекты
        """Выполнить доставку и заполнить ``usvc.public_data`` / ``private_data``.

        Бросает исключение при невозможности выдачи — менеджер переведёт заказ
        в ``failed`` и при необходимости вернёт средства.
        """
        raise NotImplementedError

    async def run_action(self, usvc, service, acc, action) -> None:  # noqa: ANN001
        """Выполнить действие ЖЦ над услугой (create/renew/stop/delete/freeze).

        :arg usvc: выданная услуга (ORM).
        :arg service: эталонная услуга (ORM).
        :arg acc: аккаунт-владелец (ORM).
        :arg action: действие из :class:`enums.ServiceAction`.
        """
        raise NotImplementedError("этот способ выдачи не поддерживает действия ЖЦ")


__all__ = ["BaseIssuer"]
