"""Менеджер плагинов ядра SaviorBill (PluginMngr)."""

from __future__ import annotations

import importlib.util
import json
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, FastAPI
from pydantic import BaseModel, Field

from security.rbac import reg_perm
from lifecycle.triggers import register_in_process_subscriber, unregister_in_process_subscribers

from .base import BasePlugin, PluginContext
from .migrator import PluginMigrator, SLUG_PATTERN

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
    import valkey.asyncio as valkey
    from core.config import AppConfig

logger = logging.getLogger("saviorbill.plugins")


class PluginPermissionSchema(BaseModel):
    key: str
    name: str
    description: str | None = None


class PluginManifestSchema(BaseModel):
    slug: str
    name: str
    version: str = "1.0.0"
    description: str = ""
    icon: str = "Plug"
    author: str = ""
    min_core_version: str | None = None
    permissions: list[PluginPermissionSchema] = Field(default_factory=list)
    settings_schema: dict[str, Any] | None = None
    admin_ui: dict[str, Any] | None = None
    client_embed: dict[str, Any] | None = None


class PluginMngr:
    """Менеджер обнаружения, миграций, жизненного цикла и роутинга плагинов ядра."""

    def __init__(
        self,
        app: FastAPI,
        plugins_dir: Path,
        db_sessionmaker: async_sessionmaker[AsyncSession],
        vk: valkey.Valkey,
        config: AppConfig,
    ) -> None:
        self.app = app
        self.plugins_dir = plugins_dir
        self.db_sessionmaker = db_sessionmaker
        self.valkey = vk
        self.config = config
        self.migrator = PluginMigrator(db_sessionmaker)

        self.active_plugins: dict[str, BasePlugin] = {}
        self.manifests: dict[str, PluginManifestSchema] = {}
        self.plugin_errors: dict[str, str] = {}
        # Зарегистрированные хэндлеры событий и роуты по каждому плагину (для аккуратной выгрузки)
        self._plugin_subscribers: dict[str, list[Any]] = {}
        self._plugin_app_routes: dict[str, list[Any]] = {}

        # Базовый префикс для динамического добавления маршрутов плагинов
        self.root_router = APIRouter(prefix="/api/v1/plugin")

    async def initialize(self) -> None:
        """Инициализация: создание каталогов, таблицы миграций и загрузка плагинов."""
        self.plugins_dir.mkdir(parents=True, exist_ok=True)
        await self.migrator.init_migration_table()
        await self.load_all()
        logger.info("PluginMngr initialized with %d active plugins", len(self.active_plugins))

    async def load_all(self) -> None:
        """Сканирование директории и загрузка всех плагинов."""
        if not self.plugins_dir.exists():
            return

        for item in sorted(self.plugins_dir.iterdir(), key=lambda x: x.name):
            if item.is_dir() and (item / "manifest.json").exists():
                try:
                    await self.load_plugin(item.name)
                except Exception as exc:
                    self.plugin_errors[item.name] = str(exc)
                    logger.error(f"Failed to load plugin '{item.name}': {exc}", exc_info=True)

    async def load_plugin(self, slug: str) -> None:
        """Загрузить и активировать один плагин по его slug."""
        if not SLUG_PATTERN.match(slug):
            raise ValueError(f"Invalid plugin slug: '{slug}'")

        if slug in self.active_plugins:
            await self.unload_plugin(slug)

        self.plugin_errors.pop(slug, None)
        plugin_dir = self.plugins_dir / slug
        manifest_path = plugin_dir / "manifest.json"

        if not manifest_path.exists():
            raise FileNotFoundError(f"Manifest not found in {plugin_dir}")

        with open(manifest_path, "r", encoding="utf-8") as f:
            raw_manifest = json.load(f)

        manifest = PluginManifestSchema.model_validate(raw_manifest)
        if manifest.slug != slug:
            raise ValueError(f"Manifest slug '{manifest.slug}' does not match directory name '{slug}'")

        self.manifests[slug] = manifest

        # 1. Применяем SQL-миграции схемы plugin_{slug}
        migrations_dir = plugin_dir / "migrations"
        await self.migrator.apply_migrations(slug, migrations_dir)

        # 2. Регистрируем права в системном реестре RBAC
        for perm in manifest.permissions:
            perm_path = f"plugins.{slug}.{perm.key}"
            reg_perm(perm_path)

        # 3. Динамический импорт plugin.py (если есть)
        entry_file = plugin_dir / "plugin.py"
        instance: BasePlugin | None = None
        handlers_list: list[Any] = []

        if entry_file.exists():
            clean_pkg_slug = slug.replace("-", "_")
            pkg_name = f"saviorbill_plugin_{clean_pkg_slug}"
            pkg_init = plugin_dir / "__init__.py"
            if not pkg_init.exists():
                pkg_init.write_text("", encoding="utf-8")

            pkg_spec = importlib.util.spec_from_file_location(
                pkg_name,
                pkg_init,
                submodule_search_locations=[str(plugin_dir)],
            )
            if pkg_spec and pkg_spec.loader:
                pkg_mod = importlib.util.module_from_spec(pkg_spec)
                sys.modules[pkg_name] = pkg_mod
                pkg_spec.loader.exec_module(pkg_mod)

            spec = importlib.util.spec_from_file_location(
                f"{pkg_name}.plugin",
                entry_file,
            )
            if not spec or not spec.loader:
                raise RuntimeError(f"Cannot load spec for {entry_file}")

            module = importlib.util.module_from_spec(spec)
            module.__package__ = pkg_name
            sys.modules[f"{pkg_name}.plugin"] = module
            spec.loader.exec_module(module)

            # Находим класс плагина (наследник BasePlugin)
            plugin_cls: type[BasePlugin] | None = None
            for attr_name in ("Plugin", f"{slug.capitalize()}Plugin"):
                candidate = getattr(module, attr_name, None)
                if isinstance(candidate, type) and issubclass(candidate, BasePlugin) and candidate is not BasePlugin:
                    plugin_cls = candidate
                    break

            if not plugin_cls:
                for attr_name in dir(module):
                    candidate = getattr(module, attr_name)
                    if (
                        isinstance(candidate, type)
                        and issubclass(candidate, BasePlugin)
                        and candidate is not BasePlugin
                    ):
                        plugin_cls = candidate
                        break

            if not plugin_cls:
                raise RuntimeError(f"No BasePlugin subclass found in {entry_file}")

            ctx = PluginContext(
                slug=slug,
                manifest=raw_manifest,
                app=self.app,
                config=self.config,
                db_sessionmaker=self.db_sessionmaker,
                valkey=self.valkey,
            )
            instance = plugin_cls(ctx)
            await instance.on_load()
            self.active_plugins[slug] = instance

            # Монтируем зарегистрированные роутеры плагина напрямую в app.router,
            # чтобы hot-reload и unload могли чисто удалять/обновлять маршруты.
            before_len = len(self.app.router.routes)
            for router, prefix, tags in instance._routers:
                # Маршрут станет: /api/v1/plugin/{slug}{prefix}
                self.app.include_router(
                    router,
                    prefix=f"{self.root_router.prefix}/{slug}{prefix}",
                    tags=tags or [f"plugin: {slug}"],
                )
            self._plugin_app_routes[slug] = list(self.app.router.routes[before_len:])
            self.app.openapi_schema = None

            # Подписываем обработчики на шину событий
            for event_name, handler in instance._subscriptions:
                register_in_process_subscriber(event_name, handler)
                handlers_list.append(handler)

            self._plugin_subscribers[slug] = handlers_list

        logger.info(f"Plugin '{slug}' v{manifest.version} loaded successfully")

    async def unload_plugin(self, slug: str) -> None:
        """Корректная выгрузка и деактивация плагина."""
        instance = self.active_plugins.get(slug)
        if instance:
            try:
                await instance.on_unload()
            except Exception as exc:
                logger.warning(f"Error in on_unload for plugin '{slug}': {exc}", exc_info=True)
            self.active_plugins.pop(slug, None)

        # Отписываем зарегистрированные хэндлеры событий
        subs = self._plugin_subscribers.pop(slug, [])
        if subs:
            unregister_in_process_subscribers(subs)

        # Удаляем маршруты плагина из FastAPI app.router
        plugin_routes = self._plugin_app_routes.pop(slug, [])
        if plugin_routes:
            route_ids = {id(r) for r in plugin_routes}
            self.app.router.routes[:] = [
                r for r in self.app.router.routes if id(r) not in route_ids
            ]
            self.app.openapi_schema = None

        # Сбрасываем модули плагина из sys.modules для корректного hot-reload кода
        clean_pkg_slug = slug.replace("-", "_")
        pkg_prefix = f"saviorbill_plugin_{clean_pkg_slug}"
        for mod_name in [
            m for m in sys.modules if m == pkg_prefix or m.startswith(f"{pkg_prefix}.")
        ]:
            sys.modules.pop(mod_name, None)

        self.manifests.pop(slug, None)
        logger.info(f"Plugin '{slug}' unloaded")

    async def reload_all(self) -> int:
        """Горячая перезагрузка всех плагинов."""
        for slug in list(self.active_plugins.keys()):
            await self.unload_plugin(slug)
        await self.load_all()
        return len(self.active_plugins)

    async def list_plugins(self) -> list[dict[str, Any]]:
        """Получить список всех плагинов (активных, с ошибками и осиротевших схем)."""
        result: list[dict[str, Any]] = []

        # 1. Все директории плагинов на диске
        found_slugs: set[str] = set()
        if self.plugins_dir.exists():
            for item in sorted(self.plugins_dir.iterdir(), key=lambda x: x.name):
                if item.is_dir() and (item / "manifest.json").exists():
                    found_slugs.add(item.name)
                    slug = item.name
                    manifest = self.manifests.get(slug)
                    is_active = slug in self.active_plugins
                    error = self.plugin_errors.get(slug)

                    # Размер схемы в БД
                    db_size = {"bytes": 0, "pretty": "0 B"}
                    try:
                        db_size = await self.migrator.get_schema_size(slug)
                    except Exception:
                        pass

                    result.append(
                        {
                            "slug": slug,
                            "name": manifest.name if manifest else slug,
                            "version": manifest.version if manifest else "unknown",
                            "description": manifest.description if manifest else "",
                            "icon": manifest.icon if manifest else "Plug",
                            "author": manifest.author if manifest else "",
                            "status": "active" if is_active else ("error" if error else "disabled"),
                            "error": error,
                            "permissions": [p.model_dump() for p in manifest.permissions] if manifest else [],
                            "has_settings": bool(manifest and manifest.settings_schema),
                            "admin_ui": manifest.admin_ui if manifest else None,
                            "client_embed": manifest.client_embed if manifest else None,
                            "db_size": db_size,
                        }
                    )

        # 2. Поиск осиротевших схем плагинов в PostgreSQL
        try:
            from sqlalchemy import text
            async with self.db_sessionmaker() as session:
                q = text("""
                    SELECT DISTINCT plugin_slug 
                    FROM public.plugin_migrations;
                """)
                rows = (await session.execute(q)).fetchall()
                for r in rows:
                    slug = r[0]
                    if (
                        slug not in found_slugs
                        and slug.replace("_", "-") not in found_slugs
                        and slug.replace("-", "_") not in found_slugs
                    ):
                        db_size = {"bytes": 0, "pretty": "0 B"}
                        try:
                            db_size = await self.migrator.get_schema_size(slug)
                        except Exception:
                            pass
                        result.append(
                            {
                                "slug": slug,
                                "name": f"{slug} (Архив данных)",
                                "version": "",
                                "description": "Файлы плагина удалены, но схема и данные в БД сохранены.",
                                "icon": "Database",
                                "author": "",
                                "status": "orphaned",
                                "error": None,
                                "permissions": [],
                                "has_settings": False,
                                "admin_ui": None,
                                "client_embed": None,
                                "db_size": db_size,
                            }
                        )
        except Exception:
            pass

        return result


__all__ = ["PluginMngr", "PluginManifestSchema", "PluginPermissionSchema"]
