"""Базовый класс и контекст для плагинов ядра SaviorBill (Core Plugins Engine)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Coroutine
from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
import valkey.asyncio as valkey

if TYPE_CHECKING:
    from fastapi import FastAPI
    from core.config import AppConfig


@dataclass(frozen=True)
class PluginContext:
    """Контекст исполнения плагина ядра."""

    slug: str
    manifest: dict[str, Any]
    app: FastAPI
    config: AppConfig
    db_sessionmaker: async_sessionmaker[AsyncSession]
    valkey: valkey.Valkey


class BasePlugin:
    """Базовый абстрактный класс плагина SaviorBill.
    
    Каждый плагин ядра наследует этот класс и реализует `on_load()` и `on_unload()`.
    """

    def __init__(self, ctx: PluginContext) -> None:
        self.ctx = ctx
        self.slug: str = ctx.slug
        self.manifest: dict[str, Any] = ctx.manifest
        self._routers: list[tuple[APIRouter, str, list[str] | None]] = []
        self._subscriptions: list[tuple[str, Callable[..., Coroutine[Any, Any, None]]]] = []

    # ==================== Жизненный цикл ====================

    async def on_load(self) -> None:
        """Вызывается при загрузке/активации плагина в ядро."""
        pass

    async def on_unload(self) -> None:
        """Вызывается при выгрузке/деактивации плагина (очистка таймеров, подписок)."""
        pass

    # ==================== Регистрация роутеров и событий ====================

    def include_router(
        self,
        router: APIRouter,
        prefix: str = "",
        tags: list[str] | None = None,
    ) -> None:
        """Зарегистрировать FastAPI роутер плагина.
        
        Роутер автоматически монтируется с базовым префиксом `/api/v1/plugin/{slug}{prefix}`.
        """
        self._routers.append((router, prefix, tags))

    def subscribe(
        self,
        event_name: str,
        handler: Callable[[dict[str, Any]], Coroutine[Any, Any, None]],
    ) -> None:
        """Подписаться на доменное событие системной шины Triggers."""
        self._subscriptions.append((event_name, handler))

    # ==================== Доступ к ресурсам ====================

    def get_db_session(self) -> AsyncSession:
        """Получить асинхронную сессию БД."""
        return self.ctx.db_sessionmaker()

    async def get_setting(self, key: str, default: Any = None) -> Any:
        """Получить значение настройки плагина из system_settings."""
        from models.system_settings import SystemSettingsMngr
        from dependencies.sec import make_secbox

        full_key = f"plugin.{self.slug}.{key}"
        async with self.get_db_session() as session:
            secbox = make_secbox(self.ctx.config)
            mngr = SystemSettingsMngr(
                session,
                self.ctx.valkey,
                secbox,
                self.ctx.config.SETTINGS_CACHE_TTL,
            )
            return await mngr.get(full_key, default)

    async def set_setting(self, key: str, value: Any) -> None:
        """Сохранить значение настройки плагина в system_settings."""
        from models.system_settings import SystemSettingsMngr
        from dependencies.sec import make_secbox

        full_key = f"plugin.{self.slug}.{key}"
        async with self.get_db_session() as session:
            secbox = make_secbox(self.ctx.config)
            mngr = SystemSettingsMngr(
                session,
                self.ctx.valkey,
                secbox,
                self.ctx.config.SETTINGS_CACHE_TTL,
            )
            await mngr.set(full_key, value)
            await session.commit()


__all__ = ["BasePlugin", "PluginContext"]
