"""Проверки при каждом старте сервиса (вызывается из ``lifespan``).

Модуль независим от ``utils.init``: первичная инициализация выполняется отдельно
(:func:`utils.init.init_system`) до вызова :func:`bootstrap`.
"""

from __future__ import annotations

import logging

import valkey.asyncio as valkey
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dependencies.sec import make_secbox
from dependencies.settings import SystemSettingsMngr
from dependencies.ratelimit import seed_rate_limits
from utils.bootstrap.access import check_access
from utils.bootstrap.integrity_check import check_integrity
from utils.config import AppConfig

log = logging.getLogger("saviorbill.bootstrap")


def _mngr(
    cfg: AppConfig, session: AsyncSession, vk: valkey.Valkey
) -> SystemSettingsMngr:
    return SystemSettingsMngr(session, vk, make_secbox(cfg), cfg.SETTINGS_CACHE_TTL)


async def bootstrap(
    cfg: AppConfig,
    sessionmaker: async_sessionmaker[AsyncSession],
    vk: valkey.Valkey,
) -> None:
    """Выполнить проверки, требуемые на каждый запуск приложения."""
    async with sessionmaker() as session:
        mngr = _mngr(cfg, session, vk)
        await check_access(mngr, cfg)
        ok = await check_integrity(session, make_secbox(cfg))
        await session.commit()
        if not ok:
            log.critical(
                "encryption integrity check failed - " "secrets can be unreadable"
            )
    # Сид ENV-дефолтов лимитов частоты в Valkey (не перетирая ручные правки).
    await seed_rate_limits(vk, cfg)


__all__ = ["bootstrap"]
