"""Начальная настройка сервиса при старте (вызывается из ``lifespan``)."""

from __future__ import annotations

import logging

import valkey.asyncio as valkey
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dependencies.sec import make_secbox
from dependencies.settings import SystemSettingsMngr
from utils.bootstrap.access import check_access
from utils.bootstrap.integrity_check import check_integrity
from utils.config import AppConfig
from utils.init import run_init

log = logging.getLogger("saviorbill.bootstrap")

# Флаг «система инициализирована» в таблице настроек.
_INIT_FLAG = "system.initialized"


def _mngr(
    cfg: AppConfig, session: AsyncSession, vk: valkey.Valkey
) -> SystemSettingsMngr:
    return SystemSettingsMngr(session, vk, make_secbox(cfg), cfg.SETTINGS_CACHE_TTL)


async def bootstrap(
    cfg: AppConfig,
    sessionmaker: async_sessionmaker[AsyncSession],
    vk: valkey.Valkey,
) -> None:
    """Выполнить начальную настройку сервиса при старте приложения."""
    # --- Первичная инициализация (один раз) ---
    async with sessionmaker() as session:
        mngr = _mngr(cfg, session, vk)
        already = await mngr.get(_INIT_FLAG)
        if already != "1":
            await run_init(session, mngr, cfg)
            await mngr.set(_INIT_FLAG, "1", is_secret=False)
            await session.commit()
        else:
            log.info("система уже инициализирована — init пропущен")

    # --- Проверки на каждый запуск ---
    async with sessionmaker() as session:
        mngr = _mngr(cfg, session, vk)
        await check_access(mngr, cfg)
        ok = await check_integrity(session, make_secbox(cfg))
        await session.commit()
        if not ok:
            log.critical(
                "проверка целостности шифрования не пройдена — "
                "секреты могут быть нечитаемы"
            )


__all__ = ["bootstrap"]
