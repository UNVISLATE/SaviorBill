"""Создание базовых системных ролей при первом запуске."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.roles import Role

log = logging.getLogger("saviorbill.init")

# Логические ключи базовых ролей → дефолтные права.
# ``{"*": True}`` — суперправо (см. utils/rbac.has_perm).
_BASE_PERMS: dict[str, dict] = {
    "owner": {"*": True},
    # Полный доступ к админ-разделам (без неявного владения системой).
    "admin": {
        "users": True,
        "roles": True,
        "services": True,
        "catalogs": True,
        "orders": True,
        "purchases": True,
        "oauth": True,
        "lua": True,
        "email": True,
        "triggers": True,
        "media": True,
        "promo": True,
    },
    # Менеджер: товары/каталоги/заказы/оплаты + промокоды + загрузка медиа.
    "manager": {
        "services": True,
        "catalogs": True,
        "orders": True,
        "purchases": True,
        "promo": True,
        "triggers": {"read": True},
        "media": {"upload": True},
    },
    # Поддержка: просмотр пользователей и заказов.
    "support": {
        "users": {"read": True},
        "orders": {"read": True},
    },
    # Обычный (верифицированный) пользователь: загрузка аватарки.
    "user": {"media": {"upload": True}},
    # Гость: только что зарегистрирован, email не подтверждён (== is_verified false).
    "guest": {"media": {"upload": True}},
    # Заблокированный: без админ-прав (доступ к своему профилю — через auth-роуты).
    "banned": {},
}

_TITLES: dict[str, str] = {
    "owner": "Owner",
    "admin": "Administrator",
    "manager": "Manager",
    "support": "Support",
    "user": "User",
    "guest": "Guest",
    "banned": "Banned",
}


async def create_base_roles(
    session: AsyncSession, names: dict[str, str]
) -> dict[str, Role]:
    """Создать недостающие базовые роли и вернуть их по логическому ключу.

    :arg names: отображение логического ключа роли (``owner`` …) на её имя в БД.
    """
    out: dict[str, Role] = {}
    for key, perms in _BASE_PERMS.items():
        name = names.get(key, key)
        role = await session.scalar(select(Role).where(Role.key == key))
        if role is None:
            # Совместимость: могла существовать одноимённая роль без ключа.
            role = await session.scalar(select(Role).where(Role.name == name))
        if role is None:
            role = Role(
                name=name,
                title=_TITLES.get(key, name.title()),
                key=key,
                is_system=True,
                perms=perms,
            )
            session.add(role)
            await session.flush()
            log.info("создана базовая роль %r (key=%s)", name, key)
        elif role.key != key:
            role.key = key
            await session.flush()
        out[key] = role
    return out


__all__ = ["create_base_roles"]
