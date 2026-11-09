"""Юнит-тесты подсистемы расширений ядра (Core Plugins Engine)."""

import json
from pathlib import Path
import pytest
from pydantic import ValidationError
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport

from plugins.base import BasePlugin, PluginContext
from plugins.manager import PluginMngr, PluginManifestSchema
from plugins.migrator import PluginMigrator, SLUG_PATTERN
from security.rbac import all_perms, has_perm

pytestmark = [pytest.mark.unit]


def test_slug_pattern():
    assert SLUG_PATTERN.match("reviews")
    assert SLUG_PATTERN.match("giveaway_1")
    assert SLUG_PATTERN.match("steam_trade_bot")
    assert SLUG_PATTERN.match("test-plugin")
    assert not SLUG_PATTERN.match("A")  # less than 2 chars, uppercase
    assert not SLUG_PATTERN.match("slug with spaces")
    assert not SLUG_PATTERN.match("slug;drop table")


def test_manifest_validation():
    valid = {
        "slug": "test_plugin",
        "name": "Тестовый плагин",
        "version": "1.2.0",
        "description": "Описание",
        "icon": "Plug",
        "permissions": [{"key": "read", "name": "Чтение"}],
        "settings_schema": {
            "title": "Настройки",
            "fields": [{"key": "enabled", "type": "boolean", "label": "Включить"}],
        },
    }
    schema = PluginManifestSchema.model_validate(valid)
    assert schema.slug == "test_plugin"
    assert schema.name == "Тестовый плагин"
    assert len(schema.permissions) == 1
    assert schema.permissions[0].key == "read"

    with pytest.raises(ValidationError):
        # Отсутствует обязательный name
        PluginManifestSchema.model_validate({"slug": "test"})


@pytest.mark.asyncio
async def test_plugin_migrator_schema_and_migrations(tmp_path: Path):
    from unittest.mock import AsyncMock, MagicMock

    session = AsyncMock()
    # Mocking execute calls
    res_mock = MagicMock()
    res_mock.fetchall.return_value = []
    res_mock.mappings.return_value.one.return_value = {"bytes": 40960, "pretty": "40 kB"}
    session.execute.return_value = res_mock

    sessionmaker = MagicMock()
    sessionmaker.return_value.__aenter__.return_value = session

    migrator = PluginMigrator(sessionmaker)

    # 1. Init table
    await migrator.init_migration_table()
    assert session.execute.called

    # 2. Migrations dir
    mig_dir = tmp_path / "migrations"
    mig_dir.mkdir()
    (mig_dir / "001_init.sql").write_text("CREATE TABLE test_table (id INT);", encoding="utf-8")

    applied = await migrator.apply_migrations("test_plugin", mig_dir)
    assert "001_init.sql" in applied

    # 3. Schema size
    size = await migrator.get_schema_size("test_plugin")
    assert size["bytes"] == 40960
    assert size["pretty"] == "40 kB"

    # 4. Drop data
    await migrator.drop_schema_data("test_plugin")
    assert session.commit.called


@pytest.mark.asyncio
async def test_plugin_manager_lifecycle(tmp_path: Path):
    from unittest.mock import AsyncMock, MagicMock

    app = FastAPI()
    session = AsyncMock()
    res_mock = MagicMock()
    res_mock.fetchall.return_value = []
    res_mock.mappings.return_value.one.return_value = {"bytes": 1024, "pretty": "1 kB"}
    session.execute.return_value = res_mock

    sm = MagicMock()
    sm.return_value.__aenter__.return_value = session
    vk = AsyncMock()

    config = MagicMock()
    config.SETTINGS_CACHE_TTL = 300

    # Создаём тестовый плагин во временной папке
    plugin_dir = tmp_path / "sample_plugin"
    plugin_dir.mkdir()

    manifest_data = {
        "slug": "sample_plugin",
        "name": "Образцовый плагин",
        "version": "1.0.0",
        "description": "Тестирование Core Plugins Engine",
        "icon": "Plug",
        "permissions": [
            {"key": "view", "name": "Просмотр"},
            {"key": "edit", "name": "Редактирование"},
        ],
        "settings_schema": {
            "title": "Настройки образцового плагина",
            "fields": [{"key": "mode", "type": "text", "label": "Режим"}],
        },
    }
    (plugin_dir / "manifest.json").write_text(json.dumps(manifest_data), encoding="utf-8")

    code = """
from fastapi import APIRouter
from plugins.base import BasePlugin

sample_router = APIRouter()

@sample_router.get("/status")
async def get_status():
    return {"status": "ok"}

class SamplePlugin(BasePlugin):
    async def on_load(self):
        self.include_router(sample_router, prefix="/api", tags=["sample"])
        self.subscribe("test.event", self.on_event)

    async def on_event(self, ctx):
        pass

    async def on_unload(self):
        pass
"""
    (plugin_dir / "plugin.py").write_text(code, encoding="utf-8")

    mngr = PluginMngr(app, tmp_path, sm, vk, config)
    await mngr.initialize()

    # Проверяем, что плагин загрузился
    assert "sample_plugin" in mngr.active_plugins
    plugin = mngr.active_plugins["sample_plugin"]
    assert plugin.slug == "sample_plugin"

    # Проверяем регистрацию прав в системном реестре RBAC
    perms = all_perms()
    assert "plugins.sample_plugin.view" in perms
    assert "plugins.sample_plugin.edit" in perms

    # Проверяем права через has_perm
    role_perms = {"plugins": {"sample_plugin": {"view": True}}}
    assert has_perm(role_perms, "plugins.sample_plugin.view")
    assert not has_perm(role_perms, "plugins.sample_plugin.edit")

    # Проверяем list_plugins
    plugin_list = await mngr.list_plugins()
    assert len(plugin_list) >= 1
    found = next((p for p in plugin_list if p["slug"] == "sample_plugin"), None)
    assert found is not None
    assert found["name"] == "Образцовый плагин"
    assert found["status"] == "active"
    assert found["has_settings"] is True

    # Проверяем динамический роутинг
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/plugin/sample_plugin/api/status")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    # Проверяем выгрузку
    await mngr.unload_plugin("sample_plugin")
    assert "sample_plugin" not in mngr.active_plugins
