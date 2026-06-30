"""DI для каталога: услуги, каталоги и Lua-скрипты."""

from __future__ import annotations

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.db import get_db_session
from models.service import ServiceMngr
from models.service_catalogs import ServiceCatalogsMngr
from models.system_scripts import SystemScriptsMngr
from utils.config import AppConfig
from utils.storage import StorageSvc


def _scripts_dir(request: Request) -> str:
    cfg: AppConfig = request.app.state.settings
    return cfg.LUA_SCRIPTS_DIR


def get_service_mngr(session: AsyncSession = Depends(get_db_session)) -> ServiceMngr:
    return ServiceMngr(session)


def get_catalog_mngr(
    session: AsyncSession = Depends(get_db_session),
) -> ServiceCatalogsMngr:
    return ServiceCatalogsMngr(session)


def get_script_mngr(
    request: Request, session: AsyncSession = Depends(get_db_session)
) -> SystemScriptsMngr:
    return SystemScriptsMngr(session, _scripts_dir(request))


def get_storage(request: Request) -> StorageSvc:
    return StorageSvc(request.app.state.settings)


__all__ = [
    "ServiceMngr",
    "ServiceCatalogsMngr",
    "SystemScriptsMngr",
    "get_service_mngr",
    "get_catalog_mngr",
    "get_script_mngr",
    "get_storage",
]
