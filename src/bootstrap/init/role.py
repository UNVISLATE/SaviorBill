"""Создание базовых системных ролей при первом запуске."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.roles import Role

log = logging.getLogger("saviorbill.init")

# Системные роли — их назначение управляется платформой автоматически
# (регистрация/верификация/бан) или они зарезервированы под встроенную логику
# на будущее. У системных ролей можно менять права (см. api/v1/admin/roles.py),
# но не более — они не подлежат обычному CRUD как пользовательские роли.
_SYSTEM_KEYS: frozenset[str] = frozenset(
    {"owner", "user", "guest", "banned", "support", "media"}
)

# Логические ключи базовых ролей → дефолтные права.
# ``{"*": True}`` — суперправо (см. utils/rbac.has_perm).
_BASE_PERMS: dict[str, dict] = {
    "owner": {"*": True},
    # Обычная (не системная) роль — создаётся как удобный дефолт, но не
    # назначается автоматически никакими условиями платформы: полностью
    # управляется через админку наравне с любой пользовательской ролью.
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
        "audit": True,
        "settings": True,
        "analytics": {"basic": {"read": True}},
        # Реалтайм-мониторинг ("Система" в админке): system.tasks.* — хвост
        # журнала media/lua тасков (billing, apiws/v1/tasks.py +
        # admin/tasks/*); system.jobs.* — realtime-логи/прогресс ffmpeg
        # (сами роуты на стороне mediaworker, см. mediaworker/src/api/logs.py);
        # system.stats.* — heartbeat/CPU/RSS инстансов (§1, api/v1/system/
        # stats.py + apiws/v1/system_stats.py). instance.read отдельно от
        # read — доступ к деталям конкретного инстанса (какая джоба сейчас
        # выполняется) закрыт от обычного summary-уровня.
        "system": {
            "tasks": {"read": True},
            "jobs": {"read": True},
            "stats": {"read": True, "instance": {"read": True}},
        },
        # Явные админ-права на медиа: "upload" — без ограничения по размеру
        # вообще; "manage_any" — доступ к preview/thumb/avatar ЧУЖОГО медиа.
        # Не совпадают с media.uploadlarge (только лимит размера) — см.
        # §2.2 AUDIT.md.
        "admin": {"media": {"upload": True, "manage_any": True}},
    },
    # Тоже не системная: удобный дефолт, назначается только вручную.
    "manager": {
        "services": True,
        "catalogs": True,
        "orders": True,
        "purchases": True,
        "promo": True,
        "triggers": {"read": True},
        "media": {"upload": True},
    },
    # Системная, зарезервирована на будущее (интеграция с AIOSupport)
    "support": {},
    # Системная, зарезервирована на будущее (медиа-партнерка)
    "media": {},
    # Обычный (верифицированный) пользователь: полный доступ к своим данным.
    "user": {"media": {"upload": True}, "user": {"*": True}},
    "guest": {"media": {"upload": True}, "user": {"*": True}},
    # Заблокированный: видит свой профиль/бан-флаг, ничего больше.
    "banned": {"user": {"profile": {"read": True}}},
}

# Базовые роли, допущенные к входу в админку по умолчанию (owner всегда,
# остальные системные/пользовательские роли — нет, доступ включается вручную).
_ADMIN_LOGIN_ALLOWED: frozenset[str] = frozenset({"owner", "admin", "manager"})

_TITLES: dict[str, str] = {
    "owner": "Owner",
    "admin": "Administrator",
    "manager": "Manager",
    "support": "Support",
    "media": "Media",
    "user": "User",
    "guest": "Guest",
    "banned": "Banned",
}


async def create_base_roles(
    session: AsyncSession, names: dict[str, str]
) -> dict[str, Role]:
    """Создать недостающие базовые роли и вернуть их по логическому ключу.

    :param session: сессия SQLAlchemy (async)
    :param names: отображение логического ключа роли (``owner`` …) на её имя в БД.
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
                is_system=key in _SYSTEM_KEYS,
                admin_login_allowed=key in _ADMIN_LOGIN_ALLOWED,
                perms=perms,
            )
            session.add(role)
            await session.flush()
            log.info("created base role %r (key=%s)", name, key)
        elif role.key != key:
            role.key = key
            await session.flush()
        out[key] = role
    return out


__all__ = ["create_base_roles"]
