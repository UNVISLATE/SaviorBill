"""Резолвер настроек, редактируемых из billing-админки (таблица ``settings``)."""

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

    async def quota_image_bytes(self) -> int:
        """Общий лимит суммарного объёма хранимых медиа (без media.upload.video)."""
        return await self.get_int(
            "media.quota.image_bytes", self.cfg.quota_image_bytes
        )

    async def quota_video_bytes(self) -> int:
        """Общий лимит суммарного объёма хранимых медиа (с media.upload.video).

        До этой настройки у ``media.upload.video`` не было вообще никакого
        потолка на суммарный объём — только на размер одного файла (см.
         HIGH-2): можно было бесконечно копить 500 MiB файлы.
        """
        return await self.get_int(
            "media.quota.video_bytes", self.cfg.quota_video_bytes
        )

    async def convert_timeout_sec(self) -> float:
        """Таймаут конвертации (0 = без ограничений/бесконечный)."""
        val = await self.get_int(
            "media.convert_timeout_sec", int(self.cfg.convert_timeout_sec)
        )
        return float(val)


__all__ = ["SettingsResolver"]
