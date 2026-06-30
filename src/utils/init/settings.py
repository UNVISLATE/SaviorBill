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
        log.info("засеяны настройки из ENV: %s", ", ".join(seeded))
    else:
        log.info("сидинг настроек: новых значений из ENV нет")
    return seeded


__all__ = ["seed_settings"]
