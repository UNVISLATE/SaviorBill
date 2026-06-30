"""Базовый класс нативных интеграций выдачи услуг."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from utils.luabus import LuaBus


class BaseIssuer:
    """Базовый способ выдачи услуги."""

    def __init__(self, session: AsyncSession, bus: LuaBus | None = None) -> None:
        self.s = session
        self.bus = bus

    async def issue(self, usvc, service, acc) -> None:  # noqa: ANN001 — ORM-объекты
        """Выполнить доставку и заполнить ``usvc.public_data`` / ``private_data``.

        Бросает исключение при невозможности выдачи — менеджер переведёт заказ
        в ``failed`` и при необходимости вернёт средства.
        """
        raise NotImplementedError


__all__ = ["BaseIssuer"]
