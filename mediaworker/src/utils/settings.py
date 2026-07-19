"""Резолвер настроек, редактируемых из billing-админки (таблица ``settings``).

billing хранит лимиты медиа-загрузки (``media.max_bytes`` и т.п.) в таблице
``settings`` и кэширует значения в Valkey под ключом ``settings:{key}`` (см.
``models/system_settings.py::SystemSettingsMngr`` в billing — он же пишет и
инвалидирует кэш при ``set()``). mediaworker живёт в том же Valkey/Postgres,
поэтому читает то же самое:

1. Valkey ``settings:{key}`` — быстрый путь, общий кэш с billing (если billing
   уже читал/писал этот ключ, значение уже тёплое, TTL — ``SETTINGS_CACHE_TTL``
   billing, по умолчанию 300с).
2. Postgres ``settings`` (read-only) — если кэш промахнулся или ещё не тёплый
   (протух по TTL, а никто в billing не перечитывал). После удачного чтения
   сами прогреваем Valkey-кэш тем же ключом (тем же соглашением), чтобы не
   бить БД на каждый запрос.
3. env (``Config``) — если настройки в БД вообще нет (не засеяна/удалена).

Так админ может поменять лимиты через ``/api/v1/admin/settings`` не
передеплоивая mediaworker.
"""

from __future__ import annotations

import valkey.asyncio as valkey

from utils.config import Config
from utils.db import DB

_CACHE_PREFIX = "settings:"
# Свой (короче) TTL для значений, прогретых мимо billing — не хотим держать
# устаревший лимит вечно, если billing давно не перечитывал эту настройку.
_WARM_TTL = 60


class SettingsResolver:
    """Читает настройку из общего кэша/БД billing, иначе — из .env."""

    def __init__(self, cfg: Config, vk: valkey.Valkey, db: DB) -> None:
        self.cfg = cfg
        self.vk = vk
        self.db = db

    async def get_int(self, key: str, default: int) -> int:
        cached = await self.vk.get(_CACHE_PREFIX + key)
        if cached is not None:
            try:
                return int(cached)
            except ValueError:
                pass  # повреждённое значение в кэше — идём в БД

        raw = await self.db.setting(key)
        if raw is not None:
            try:
                value = int(raw)
            except ValueError:
                return default
            await self.vk.set(_CACHE_PREFIX + key, raw, ex=_WARM_TTL)
            return value

        return default

    # --- удобные шорткаты для конкретных лимитов медиа --------------------

    async def small_max_bytes(self) -> int:
        return await self.get_int("media.small_max_bytes", self.cfg.small_max_bytes)

    async def max_bytes(self) -> int:
        return await self.get_int("media.max_bytes", self.cfg.max_bytes)

    async def uploads_per_hour(self) -> int:
        return await self.get_int(
            "media.uploads_per_hour", self.cfg.uploads_per_hour
        )

    async def user_media_limit(self) -> int:
        return await self.get_int("user.media.limit", self.cfg.user_media_limit)


__all__ = ["SettingsResolver"]
