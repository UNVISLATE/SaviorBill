"""Реестр способов выдачи услуг."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from enums import Delivery
from lifecycle.delivery.base import BaseIssuer
from lifecycle.delivery.provider.key_service import KeyService
from lua.bus import LuaBus
from security.sec.box import SecBox

# Нативные (не-lua) способы доставки. Lua — не здесь: модуль
# ``lua.integrations.delivery`` импортирует ``lifecycle.delivery.base``
# напрямую (сам issuer — lua-адаптер к этому реестру), поэтому импорт
# LuaService на уровне модуля здесь дал бы цикл
# lifecycle.delivery -> lua.integrations.delivery -> lifecycle.delivery;
# получаем его лениво в get_issuer().
_NATIVE_ISSUERS: dict[str, type[BaseIssuer]] = {
    Delivery.KEY: KeyService,
}


def known_delivery_kinds() -> tuple[str, ...]:
    """Зарегистрированные способы доставки (для валидации схем услуг).

    Тот же набор ключей, что понимает :func:`get_issuer` — новый нативный
    способ доставки добавляется регистрацией issuer'а в ``_NATIVE_ISSUERS``;
    lua уже покрыт дефолтом ``get_issuer``.
    """
    return (*_NATIVE_ISSUERS.keys(), Delivery.LUA)


def get_issuer(
    delivery: str,
    session: AsyncSession,
    bus: LuaBus | None = None,
    box: SecBox | None = None,
) -> BaseIssuer:
    """Вернуть issuer под способ доставки (по умолчанию — Lua)."""
    cls = _NATIVE_ISSUERS.get(delivery)
    if cls is None:
        from lua.integrations.delivery import LuaService

        cls = LuaService
    return cls(session, bus, box)


__all__ = [
    "BaseIssuer",
    "KeyService",
    "get_issuer",
    "known_delivery_kinds",
]
