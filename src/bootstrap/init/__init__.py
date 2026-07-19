"""Инициализация первого запуска: роли, владелец, секреты, сид настроек.

Полностью независимый модуль. Не знает про ``bootstrap`` и наоборот.
Точка входа для ``lifespan`` — :func:`init_system` (сама решает по флагу, нужен ли
запуск ``run_init``).
"""

from __future__ import annotations

import asyncio
import logging
import uuid

import valkey.asyncio as valkey
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dependencies.sec import make_secbox
from dependencies.settings import SystemSettingsMngr
from core.config import AppConfig
from bootstrap.init.email_templates import seed_email_templates
from bootstrap.init.owner import create_owner
from bootstrap.init.role import create_base_roles
from bootstrap.init.secret import harden_secret
from bootstrap.init.settings import seed_settings

log = logging.getLogger("saviorbill.init")

# Флаг «система инициализирована» в таблице настроек.
_INIT_FLAG = "system.initialized"

# Распределённая блокировка первичной инициализации (Valkey SET NX). Защищает от
# гонки, когда несколько реплик billing стартуют одновременно: без неё обе прочли
# бы флаг = null и обе запустили run_init (дубли ролей/владельца → IntegrityError).
_INIT_LOCK = "system:init:lock"
_INIT_LOCK_TTL = 120
_INIT_WAIT_STEP = 0.5
_INIT_WAIT_MAX = 120

# Логические ключи базовых ролей -> атрибуты ENV с их именами.
_ROLE_ENV: dict[str, str] = {
    "owner": "ROLE_OWNER",
    "admin": "ROLE_ADMIN",
    "manager": "ROLE_MANAGER",
    "support": "ROLE_SUPPORT",
    "media": "ROLE_MEDIA",
    "user": "ROLE_USER",
    "guest": "ROLE_GUEST",
    "banned": "ROLE_BANNED",
}


async def _role_names(cfg: AppConfig) -> dict[str, str]:
    """Собрать имена базовых ролей из ENV (только на момент первого запуска).

    Раньше значение сначала читалось из ``settings`` (``role.{key}``), но эта
    settings-копия никогда не перечитывалась после инициализации (роль уже
    существует в БД под этим именем) — только засоряла admin Raw Settings
    мёртвыми "марками", выглядящими редактируемыми без всякого эффекта.
    Теперь источник ровно один — ENV, и он нигде не дублируется в БД.
    """
    return {key: getattr(cfg, env_attr) for key, env_attr in _ROLE_ENV.items()}


async def run_init(
    session: AsyncSession, mngr: SystemSettingsMngr, cfg: AppConfig
) -> None:
    """Выполнить первичную инициализацию системы (в рамках переданной сессии)."""
    log.info("initial initialization of the system...")
    await seed_settings(mngr, cfg)
    await seed_email_templates(session, cfg)
    names = await _role_names(cfg)
    roles = await create_base_roles(session, names)
    await create_owner(session, cfg, roles["owner"])
    harden_secret(cfg)
    log.info("initial initialization completed")


def _mngr(
    cfg: AppConfig, session: AsyncSession, vk: valkey.Valkey
) -> SystemSettingsMngr:
    return SystemSettingsMngr(session, vk, make_secbox(cfg), cfg.SETTINGS_CACHE_TTL)


async def _flag_set(cfg: AppConfig, sessionmaker, vk: valkey.Valkey) -> bool:
    """Проверить флаг ``system.initialized`` в свежей сессии."""
    async with sessionmaker() as session:
        return await _mngr(cfg, session, vk).get(_INIT_FLAG) == "1"


async def _wait_initialized(cfg: AppConfig, sessionmaker, vk: valkey.Valkey) -> None:
    """Дождаться, пока флаг инициализации выставит другой экземпляр."""
    waited = 0.0
    while waited < _INIT_WAIT_MAX:
        if await _flag_set(cfg, sessionmaker, vk):
            log.info("initialization was performed by another instance — continue")
            return
        await asyncio.sleep(_INIT_WAIT_STEP)
        waited += _INIT_WAIT_STEP
    log.warning(
        "waiting for initialization has exceeded %ss — we continue without guarantee",
        _INIT_WAIT_MAX,
    )


async def _release_lock(vk: valkey.Valkey, token: str) -> None:
    """Освободить лок, только если он всё ещё наш (проверка token)."""
    cur = await vk.get(_INIT_LOCK)
    cur = cur.decode() if isinstance(cur, bytes) else cur
    if cur == token:
        await vk.delete(_INIT_LOCK)


async def init_system(
    cfg: AppConfig,
    sessionmaker: async_sessionmaker[AsyncSession],
    vk: valkey.Valkey,
) -> None:
    """Выполнить первичную инициализацию один раз (идемпотентно по флагу).

    Независимая точка входа: сама открывает сессию, проверяет флаг
    ``system.initialized`` и при необходимости вызывает :func:`run_init`.

    Гонку между репликами billing, стартующими одновременно, снимает
    распределённый лок ``SET system:init:lock <token> NX EX``: победитель
    выполняет :func:`run_init`, остальные ждут появления флага. Без лока обе
    реплики прочли бы флаг = ``null`` и запустили бы ``run_init`` дважды
    (дубли ролей/владельца → ``IntegrityError``).

    :arg cfg: конфигурация приложения.
    :arg sessionmaker: фабрика сессий БД.
    :arg vk: клиент Valkey (для менеджера настроек и распределённого лока).
    """
    if await _flag_set(cfg, sessionmaker, vk):
        log.info("the system has already been initialized — init skipped")
        return

    token = uuid.uuid4().hex
    got_lock = bool(await vk.set(_INIT_LOCK, token, nx=True, ex=_INIT_LOCK_TTL))
    if not got_lock:
        log.info("initialization is performed by another instance — waiting...")
        await _wait_initialized(cfg, sessionmaker, vk)
        return

    try:
        async with sessionmaker() as session:
            mngr = _mngr(cfg, session, vk)
            if await mngr.get(_INIT_FLAG) == "1":
                log.info("the system has already been initialized — init skipped")
                return
            await run_init(session, mngr, cfg)
            await mngr.set(_INIT_FLAG, "1", is_secret=False)
            await session.commit()
    finally:
        await _release_lock(vk, token)


__all__ = ["run_init", "init_system"]
