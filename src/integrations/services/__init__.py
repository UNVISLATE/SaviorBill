"""Реестр способов выдачи услуг."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from enums import Delivery
from integrations.services.base import BaseIssuer
from integrations.services.provider import KeyService, LuaService
from utils.luabus import LuaBus

_ISSUERS: dict[str, type[BaseIssuer]] = {
    Delivery.KEY: KeyService,
    Delivery.LUA: LuaService,
}


def get_issuer(
    delivery: str, session: AsyncSession, bus: LuaBus | None = None
) -> BaseIssuer:
    """Вернуть issuer под способ доставки (по умолчанию — Lua)."""
    cls = _ISSUERS.get(delivery, LuaService)
    return cls(session, bus)


__all__ = ["BaseIssuer", "KeyService", "LuaService", "get_issuer"]
