"""Инициализация первого запуска: роли, владелец, секреты, сид настроек.

Полностью независимый модуль. Не знает про ``utils.bootstrap`` и наоборот.
Точка входа для ``lifespan`` — :func:`init_system` (сама решает по флагу, нужен ли
запуск ``run_init``).
"""

from __future__ import annotations

import logging

import valkey.asyncio as valkey
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dependencies.sec import make_secbox
from dependencies.settings import SystemSettingsMngr
from utils.config import AppConfig
from utils.init.email_templates import seed_email_templates
from utils.init.lua_scripts import seed_lua_scripts
from utils.init.owner import create_owner
from utils.init.role import create_base_roles
from utils.init.secret import harden_secret
from utils.init.settings import seed_settings

log = logging.getLogger("saviorbill.init")

# Флаг «система инициализирована» в таблице настроек.
_INIT_FLAG = "system.initialized"

# Логические ключи базовых ролей -> атрибуты ENV с их именами.
_ROLE_ENV: dict[str, str] = {
    "owner": "ROLE_OWNER",
    "admin": "ROLE_ADMIN",
    "manager": "ROLE_MANAGER",
    "support": "ROLE_SUPPORT",
    "user": "ROLE_USER",
    "guest": "ROLE_GUEST",
    "banned": "ROLE_BANNED",
}


async def _role_names(mngr: SystemSettingsMngr, cfg: AppConfig) -> dict[str, str]:
    """Собрать имена базовых ролей: из settings, иначе из ENV-дефолта."""
    names: dict[str, str] = {}
    for key, env_attr in _ROLE_ENV.items():
        names[key] = await mngr.get(f"role.{key}") or getattr(cfg, env_attr)
    return names


async def run_init(
    session: AsyncSession, mngr: SystemSettingsMngr, cfg: AppConfig
) -> None:
    """Выполнить первичную инициализацию системы (в рамках переданной сессии)."""
    log.info("первичная инициализация системы…")
    await seed_settings(mngr, cfg)
    await seed_email_templates(session, cfg)
    await seed_lua_scripts(session, cfg)
    names = await _role_names(mngr, cfg)
    roles = await create_base_roles(session, names)
    await create_owner(session, cfg, roles["owner"])
    harden_secret(cfg)
    log.info("первичная инициализация завершена")


def _mngr(
    cfg: AppConfig, session: AsyncSession, vk: valkey.Valkey
) -> SystemSettingsMngr:
    return SystemSettingsMngr(session, vk, make_secbox(cfg), cfg.SETTINGS_CACHE_TTL)


async def init_system(
    cfg: AppConfig,
    sessionmaker: async_sessionmaker[AsyncSession],
    vk: valkey.Valkey,
) -> None:
    """Выполнить первичную инициализацию один раз (идемпотентно по флагу).

    Независимая точка входа: сама открывает сессию, проверяет флаг
    ``system.initialized`` и при необходимости вызывает :func:`run_init`.

    :arg cfg: конфигурация приложения.
    :arg sessionmaker: фабрика сессий БД.
    :arg vk: клиент Valkey (для менеджера настроек).
    """
    async with sessionmaker() as session:
        mngr = _mngr(cfg, session, vk)
        already = await mngr.get(_INIT_FLAG)
        if already == "1":
            log.info("система уже инициализирована — init пропущен")
            return
        await run_init(session, mngr, cfg)
        await mngr.set(_INIT_FLAG, "1", is_secret=False)
        await session.commit()


__all__ = ["run_init", "init_system"]
