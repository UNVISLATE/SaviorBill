"""DI для системных настроек."""

from __future__ import annotations

import valkey.asyncio as valkey
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.db import get_db_session
from dependencies.sec import make_secbox
from dependencies.valkey import get_valkey_client
from models.system_settings import SystemSettingsMngr
from core.config import AppConfig


def get_settings_mngr(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    vk: valkey.Valkey = Depends(get_valkey_client),
) -> SystemSettingsMngr:
    cfg: AppConfig = request.app.state.settings
    return SystemSettingsMngr(session, vk, make_secbox(cfg), cfg.SETTINGS_CACHE_TTL)


__all__ = ["SystemSettingsMngr", "get_settings_mngr"]
