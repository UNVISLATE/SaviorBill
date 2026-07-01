"""Системные настройки (SystemSettingsModel) + менеджер (SystemSettingsMngr)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import valkey.asyncio as valkey
from sqlalchemy import func, Boolean, DateTime, String, Text, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from models import Base
from utils.datetime_utils import utc_now
from utils.sec.box import SecBox
from utils.settings_def import SettingDef, by_key, seed_defs

# Префикс ключей кэша настроек в Valkey.
_CACHE = "settings:"


class SystemSettingsModel(Base):
    """Настройка системы вида ключ-значение"""

    __tablename__ = "settings"

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        server_default=func.now(),
        nullable=False,
    )

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_secret: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class SystemSettingsMngr:
    """Чтение/запись системных настроек с кэшем в Valkey."""

    def __init__(
        self,
        session: AsyncSession,
        vk: valkey.Valkey,
        box: SecBox,
        cache_ttl: int = 300,
    ) -> None:
        self.s = session
        self.vk = vk
        self.box = box
        self.cache_ttl = cache_ttl

    # --- чтение -----------------------------------------------------------
    async def get(self, key: str, default: str | None = None) -> str | None:
        """Получить строковое значение настройки (cache-aside через Valkey)."""
        cached = await self.vk.get(_CACHE + key)
        if cached is not None:
            return cached

        row = await self.s.get(SystemSettingsModel, key)
        if row is None or row.value is None:
            return default

        value = self.box.open(row.value) if row.is_secret else row.value
        await self.vk.set(_CACHE + key, value, ex=self.cache_ttl)
        return value

    async def get_typed(self, key: str, default: Any = None) -> Any:
        """Получить значение, приведённое к типу из каталога настроек."""
        raw = await self.get(key)
        if raw is None:
            return default
        spec = by_key(key)
        return spec.cast(raw) if spec else raw

    async def get_int(self, key: str, default: int | None = None) -> int | None:
        raw = await self.get(key)
        return int(raw) if raw is not None else default

    async def get_bool(self, key: str, default: bool = False) -> bool:
        raw = await self.get(key)
        if raw is None:
            return default
        return raw.strip().lower() in ("1", "true", "yes", "on")

    async def get_group(self, prefix: str) -> dict[str, str]:
        """Все настройки с заданным префиксом ключа (например ``smtp.``)."""
        rows = await self.s.scalars(
            select(SystemSettingsModel).where(
                SystemSettingsModel.key.startswith(prefix)
            )
        )
        out: dict[str, str] = {}
        for row in rows:
            if row.value is None:
                continue
            out[row.key] = self.box.open(row.value) if row.is_secret else row.value
        return out

    # --- запись -----------------------------------------------------------
    async def set(
        self, key: str, value: str | None, is_secret: bool | None = None
    ) -> None:
        """Записать настройку в БД и синхронизировать кэш Valkey.

        ``is_secret=None`` — взять признак секретности из каталога настроек
        (по умолчанию ``False`` для незарегистрированных ключей).
        """
        if is_secret is None:
            spec = by_key(key)
            is_secret = spec.secret if spec else False

        row = await self.s.get(SystemSettingsModel, key)
        stored = self.box.seal(value) if (is_secret and value is not None) else value
        if row is None:
            row = SystemSettingsModel(key=key, value=stored, is_secret=is_secret)
            self.s.add(row)
        else:
            row.value = stored
            row.is_secret = is_secret
        await self.s.flush()

        if value is None:
            await self.vk.delete(_CACHE + key)
        else:
            await self.vk.set(_CACHE + key, value, ex=self.cache_ttl)

    async def invalidate(self, key: str) -> None:
        """Сбросить кэш настройки (например, после внешней правки в БД)."""
        await self.vk.delete(_CACHE + key)

    # --- сидинг из окружения ---------------------------------------------
    async def seed_from_env(self, cfg) -> list[str]:
        """Засеять отсутствующие настройки из окружения (первый запуск).

        Возвращает список засеянных ключей. Идемпотентно: значения, уже
        присутствующие в БД, не трогаются.
        """
        seeded: list[str] = []
        for spec in seed_defs():
            if await self.s.get(SystemSettingsModel, spec.key) is not None:
                continue
            value = self._env_value(cfg, spec)
            if value is None:
                continue
            await self.set(spec.key, value, is_secret=spec.secret)
            seeded.append(spec.key)
        return seeded

    @staticmethod
    def _env_value(cfg, spec: SettingDef) -> str | None:
        """Достать значение из конфига и привести к строке для хранения."""
        raw = getattr(cfg, spec.source, None) if spec.source else None
        if raw is None:
            return None
        if isinstance(raw, bool):
            return "1" if raw else "0"
        return str(raw)


__all__ = ["SystemSettingsModel", "SystemSettingsMngr"]
