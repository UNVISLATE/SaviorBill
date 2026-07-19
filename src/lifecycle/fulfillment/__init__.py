"""Реестр способов выдачи услуг."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from enums import Delivery
from lifecycle.fulfillment.base import BaseIssuer
from lifecycle.fulfillment.provider import KeyService, LuaService
from lua.bus import LuaBus
from security.sec.box import SecBox

_ISSUERS: dict[str, type[BaseIssuer]] = {
    Delivery.KEY: KeyService,
    Delivery.LUA: LuaService,
}


def known_delivery_kinds() -> tuple[str, ...]:
    """Зарегистрированные способы доставки (для валидации схем услуг).

    Тот же реестр, что использует :func:`get_issuer` для диспетчеризации
    выдачи — новый способ доставки добавляется регистрацией issuer'а здесь,
    без правки enum'ов/схем в нескольких местах.
    """
    return tuple(_ISSUERS.keys())


def get_issuer(
    delivery: str,
    session: AsyncSession,
    bus: LuaBus | None = None,
    box: SecBox | None = None,
) -> BaseIssuer:
    """Вернуть issuer под способ доставки (по умолчанию — Lua)."""
    cls = _ISSUERS.get(delivery, LuaService)
    return cls(session, bus, box)


__all__ = [
    "BaseIssuer",
    "KeyService",
    "LuaService",
    "get_issuer",
    "known_delivery_kinds",
]
