"""DI для загрузки медиа: хранилище и менеджер записей."""

from __future__ import annotations

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.db import get_db_session
from models.system_media import SystemMediaMngr
from utils.config import AppConfig
from utils.storage import StorageSvc


def get_storage_svc(request: Request) -> StorageSvc:
    cfg: AppConfig = request.app.state.settings
    return StorageSvc(cfg)


def get_media_mngr(
    session: AsyncSession = Depends(get_db_session),
) -> SystemMediaMngr:
    return SystemMediaMngr(session)


__all__ = ["get_storage_svc", "get_media_mngr"]
