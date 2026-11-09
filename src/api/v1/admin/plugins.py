"""Административный API управления плагинами ядра SaviorBill."""

from __future__ import annotations

import json
import logging
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from dependencies.rbac import require_any_perm, require_perm
from dependencies.settings import SystemSettingsMngr, get_settings_mngr
from plugins.migrator import SLUG_PATTERN

logger = logging.getLogger("saviorbill.admin.plugins")

router = APIRouter()


class PluginSettingsPatchRequest(BaseModel):
    settings: dict[str, Any]


@router.get(
    "",
    summary="Список установленных плагинов ядра",
    dependencies=[Depends(require_any_perm("plugins.manage", "settings.read", "settings.raw.read"))],
)
async def list_plugins(request: Request) -> list[dict[str, Any]]:
    """Возвращает список всех обнаруженных плагинов, их статус, права и размер в БД."""
    mngr = getattr(request.app.state, "plugin_mngr", None)
    if not mngr:
        return []
    return await mngr.list_plugins()


@router.get(
    "/{slug}/settings",
    summary="Получить схему и значения настроек плагина",
    dependencies=[Depends(require_any_perm("plugins.manage", "settings.read", "settings.raw.read"))],
)
async def get_plugin_settings(
    slug: str,
    request: Request,
    sm: SystemSettingsMngr = Depends(get_settings_mngr),
) -> dict[str, Any]:
    """Возвращает декларативную схему настроек плагина и текущие значения."""
    if not SLUG_PATTERN.match(slug):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid plugin slug")

    mngr = getattr(request.app.state, "plugin_mngr", None)
    manifest = mngr.manifests.get(slug) if mngr else None

    # Читаем все существующие настройки с префиксом plugin.{slug}.*
    prefix = f"plugin.{slug}."
    group_settings = await sm.get_group("plugin")
    values: dict[str, Any] = {}
    for k, v in group_settings.items():
        if k.startswith(prefix):
            sub_key = k[len(prefix):]
            try:
                values[sub_key] = json.loads(v)
            except Exception:
                values[sub_key] = v

    return {
        "slug": slug,
        "name": manifest.name if manifest else slug,
        "settings_schema": manifest.settings_schema if manifest else None,
        "values": values,
    }


@router.patch(
    "/{slug}/settings",
    summary="Обновить настройки плагина",
    dependencies=[Depends(require_any_perm("plugins.manage", "settings.edit", "settings.raw.edit"))],
)
async def update_plugin_settings(
    slug: str,
    payload: PluginSettingsPatchRequest,
    sm: SystemSettingsMngr = Depends(get_settings_mngr),
) -> dict[str, Any]:
    """Сохранить значения параметров плагина в системные настройки."""
    if not SLUG_PATTERN.match(slug):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid plugin slug")

    for k, v in payload.settings.items():
        full_key = f"plugin.{slug}.{k}"
        str_val = json.dumps(v) if not isinstance(v, str) else v
        await sm.set(full_key, str_val)

    await sm.s.commit()
    logger.info("Updated %d settings for plugin '%s'", len(payload.settings), slug)
    return {"ok": True, "updated": len(payload.settings)}


@router.post(
    "/reindex",
    summary="Горячая перезагрузка всех плагинов",
    dependencies=[Depends(require_any_perm("plugins.manage", "settings.edit"))],
)
async def reindex_plugins(request: Request) -> dict[str, Any]:
    """Выгружает и заново сканирует/инициализирует все плагины без перезагрузки бэкенда."""
    mngr = getattr(request.app.state, "plugin_mngr", None)
    if not mngr:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Plugin manager not available")

    count = await mngr.reload_all()
    return {"ok": True, "loaded_count": count}


@router.delete(
    "/{slug}/data",
    summary="Очистить данные плагина в БД (DROP SCHEMA)",
    dependencies=[Depends(require_perm("plugins.manage"))],
)
async def drop_plugin_data(slug: str, request: Request) -> dict[str, Any]:
    """Полностью удаляет схему плагина plugin_{slug} и его настройки. Необратимо."""
    if not SLUG_PATTERN.match(slug):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid plugin slug")

    mngr = getattr(request.app.state, "plugin_mngr", None)
    if not mngr:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Plugin manager not available")

    # Если плагин всё ещё активен, сначала выгружаем его
    if slug in mngr.active_plugins:
        await mngr.unload_plugin(slug)

    await mngr.migrator.drop_schema_data(slug)
    logger.warning("Dropped all database data for plugin '%s'", slug)
    return {"ok": True, "dropped": f"plugin_{slug}"}
