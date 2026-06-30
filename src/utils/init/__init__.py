"""Инициализация первого запуска: роли, владелец, секреты, сид настроек."""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.settings import SystemSettingsMngr
from utils.config import AppConfig
from utils.init.owner import create_owner
from utils.init.role import create_base_roles
from utils.init.secret import harden_secret
from utils.init.settings import seed_settings

log = logging.getLogger("saviorbill.init")

# Логические ключи базовых ролей ↔ атрибуты ENV с их именами.
_ROLE_ENV: dict[str, str] = {
    "owner": "ROLE_OWNER",
    "admin": "ROLE_ADMIN",
    "manager": "ROLE_MANAGER",
    "support": "ROLE_SUPPORT",
    "user": "ROLE_USER",
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
    names = await _role_names(mngr, cfg)
    roles = await create_base_roles(session, names)
    await create_owner(session, cfg, roles["owner"])
    harden_secret(cfg)
    log.info("первичная инициализация завершена")


__all__ = ["run_init"]
