"""Менеджер настроек (key-value) с кэшированием в Valkey.

Настройки лежат в таблице ``settings`` (БД — источник истины). Чтения проходят
через кэш Valkey; запись синхронно инвалидирует/обновляет кэш. Секретные
значения (``is_secret``) шифруются в БД через :class:`SecBox`.
"""

from __future__ import annotations

import valkey.asyncio as valkey
from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.db import get_db_session
from dependencies.valkey import get_valkey_client
from models.setting import Setting
from utils.config import AppConfig
from utils.sec.box import SecBox

# Префикс и TTL ключей кэша настроек в Valkey.
_CACHE = "settings:"
_CACHE_TTL = 300

# Ключи настроек SMTP.
SMTP_KEYS = {
    "smtp.host": False,
    "smtp.port": False,
    "smtp.user": False,
    "smtp.pass": True,
    "smtp.from": False,
    "smtp.tls": False,
}


class SettingsMngr:
    """Чтение/запись системных настроек с кэшем в Valkey."""

    def __init__(self, session: AsyncSession, vk: valkey.Valkey, box: SecBox) -> None:
        self.s = session
        self.vk = vk
        self.box = box

    async def get(self, key: str, default: str | None = None) -> str | None:
        """Получить значение настройки (cache-aside через Valkey)."""
        cached = await self.vk.get(_CACHE + key)
        if cached is not None:
            return cached

        row = await self.s.get(Setting, key)
        if row is None or row.value is None:
            return default

        value = self.box.open(row.value) if row.is_secret else row.value
        await self.vk.set(_CACHE + key, value, ex=_CACHE_TTL)
        return value

    async def get_group(self, prefix: str) -> dict[str, str]:
        """Все настройки с заданным префиксом ключа (например ``smtp.``)."""
        rows = await self.s.scalars(
            select(Setting).where(Setting.key.startswith(prefix))
        )
        out: dict[str, str] = {}
        for row in rows:
            if row.value is None:
                continue
            out[row.key] = self.box.open(row.value) if row.is_secret else row.value
        return out

    async def set(self, key: str, value: str | None, is_secret: bool = False) -> None:
        """Записать настройку в БД и синхронизировать кэш Valkey."""
        row = await self.s.get(Setting, key)
        stored = self.box.seal(value) if (is_secret and value is not None) else value
        if row is None:
            row = Setting(key=key, value=stored, is_secret=is_secret)
            self.s.add(row)
        else:
            row.value = stored
            row.is_secret = is_secret
        await self.s.flush()

        # Синхронизация кэша актуальным (расшифрованным) значением.
        if value is None:
            await self.vk.delete(_CACHE + key)
        else:
            await self.vk.set(_CACHE + key, value, ex=_CACHE_TTL)

    async def seed_smtp(self, cfg: AppConfig) -> None:
        """Засеять SMTP-настройки из окружения, если их ещё нет в БД."""
        exists = await self.s.scalar(
            select(Setting.key).where(Setting.key.startswith("smtp."))
        )
        if exists is not None or not cfg.SMTP_HOST:
            return
        await self.set("smtp.host", cfg.SMTP_HOST)
        await self.set("smtp.port", str(cfg.SMTP_PORT))
        await self.set("smtp.user", cfg.SMTP_USER)
        await self.set("smtp.pass", cfg.SMTP_PASS, is_secret=True)
        await self.set("smtp.from", cfg.SMTP_FROM or cfg.SMTP_USER)
        await self.set("smtp.tls", "1" if cfg.SMTP_TLS else "0")


def get_settings_mngr(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    vk: valkey.Valkey = Depends(get_valkey_client),
) -> SettingsMngr:
    cfg: AppConfig = request.app.state.settings
    return SettingsMngr(session, vk, SecBox(cfg.SECRETS_KEY))


__all__ = ["SettingsMngr", "get_settings_mngr", "SMTP_KEYS"]
