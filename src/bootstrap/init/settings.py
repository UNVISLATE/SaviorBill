"""Сидинг разовых настроек из ENV в таблицу ``settings``."""

from __future__ import annotations

import logging

from dependencies.settings import SystemSettingsMngr
from utils.config import AppConfig

log = logging.getLogger("saviorbill.init")


async def seed_settings(mngr: SystemSettingsMngr, cfg: AppConfig) -> list[str]:
    """Засеять отсутствующие настройки из ENV. Возвращает список ключей."""
    seeded = await mngr.seed_from_env(cfg)
    if seeded:
        log.info("Setup ENV init-settings (seed): %s", ", ".join(seeded))
    else:
        log.info("Setup ENV init-settings (seed): nothing to seed")
    return seeded


__all__ = ["seed_settings"]
