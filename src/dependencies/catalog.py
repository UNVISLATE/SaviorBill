"""Менеджеры каталога: услуги, каталоги и Lua-скрипты."""

from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.db import get_db_session
from models.luadb import LuaScript
from models.service import Service
from models.svc_catalog import SvcCatalog
from schemas.catalog import ScriptIn
from utils.config import AppConfig
from utils.storage import StorageSvc


class ServiceMngr:
    """Доступ к каталогу услуг и их администрирование."""

    def __init__(self, session: AsyncSession) -> None:
        self.s = session

    async def list_active(self, catalog_id: int | None = None) -> list[Service]:
        stmt = select(Service).where(Service.is_active.is_(True))
        if catalog_id is not None:
            stmt = stmt.where(Service.catalog_id == catalog_id)
        rows = await self.s.scalars(stmt.order_by(Service.id))
        return list(rows)

    async def list_all(self) -> list[Service]:
        rows = await self.s.scalars(select(Service).order_by(Service.id))
        return list(rows)

    async def by_id(self, service_id: int) -> Service | None:
        return await self.s.get(Service, service_id)

    async def get_active(self, service_id: int) -> Service:
        svc = await self.by_id(service_id)
        if svc is None or not svc.is_active:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "услуга не найдена")
        return svc

    async def create(self, data: dict) -> Service:
        if await self.s.scalar(select(Service).where(Service.slug == data["slug"])):
            raise HTTPException(status.HTTP_409_CONFLICT, "slug услуги занят")
        svc = Service(**data)
        self.s.add(svc)
        await self.s.flush()
        return svc

    async def update(self, service_id: int, data: dict) -> Service:
        svc = await self.by_id(service_id)
        if svc is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "услуга не найдена")
        for field, value in data.items():
            setattr(svc, field, value)
        await self.s.flush()
        return svc


class CatalogMngr:
    """CRUD иерархических каталогов услуг."""

    def __init__(self, session: AsyncSession) -> None:
        self.s = session

    async def list_all(self) -> list[SvcCatalog]:
        rows = await self.s.scalars(
            select(SvcCatalog).order_by(SvcCatalog.sort, SvcCatalog.id)
        )
        return list(rows)

    async def by_id(self, catalog_id: int) -> SvcCatalog | None:
        return await self.s.get(SvcCatalog, catalog_id)

    async def create(self, data: dict) -> SvcCatalog:
        if await self.s.scalar(
            select(SvcCatalog).where(SvcCatalog.slug == data["slug"])
        ):
            raise HTTPException(status.HTTP_409_CONFLICT, "slug каталога занят")
        parent_id = data.get("parent_id")
        if parent_id is not None and await self.by_id(parent_id) is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "родительский каталог не найден"
            )
        cat = SvcCatalog(**data)
        self.s.add(cat)
        await self.s.flush()
        return cat

    async def update(self, catalog_id: int, data: dict) -> SvcCatalog:
        cat = await self.by_id(catalog_id)
        if cat is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "каталог не найден")
        if data.get("parent_id") == catalog_id:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "каталог не может быть сам себе родителем"
            )
        for field, value in data.items():
            setattr(cat, field, value)
        await self.s.flush()
        return cat

    async def delete(self, catalog_id: int) -> None:
        cat = await self.by_id(catalog_id)
        if cat is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "каталог не найден")
        await self.s.delete(cat)
        await self.s.flush()


class ScriptMngr:
    """Регистрация и хранение Lua-скриптов в монтируемой папке."""

    def __init__(self, session: AsyncSession, scripts_dir: str) -> None:
        self.s = session
        self.dir = Path(scripts_dir)

    async def list_all(self) -> list[LuaScript]:
        rows = await self.s.scalars(select(LuaScript).order_by(LuaScript.id))
        return list(rows)

    async def by_slug(self, slug: str) -> LuaScript | None:
        return await self.s.scalar(select(LuaScript).where(LuaScript.slug == slug))

    async def create(self, data: ScriptIn) -> LuaScript:
        """Записать тело скрипта в файл и сохранить карту в БД."""
        if await self.by_slug(data.slug):
            raise HTTPException(status.HTTP_409_CONFLICT, "slug скрипта занят")

        # Защита от выхода за пределы папки скриптов.
        target = (self.dir / data.filename).resolve()
        if not str(target).startswith(str(self.dir.resolve())):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "недопустимый путь файла")

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(data.code, encoding="utf-8")

        row = LuaScript(
            slug=data.slug,
            name=data.name,
            kind=data.kind,
            filename=data.filename,
            sha256=hashlib.sha256(data.code.encode()).hexdigest(),
            description=data.description,
        )
        self.s.add(row)
        await self.s.flush()
        return row

    async def by_id(self, script_id: int) -> LuaScript | None:
        return await self.s.get(LuaScript, script_id)

    def _safe_target(self, filename: str) -> Path:
        target = (self.dir / filename).resolve()
        if not str(target).startswith(str(self.dir.resolve())):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "недопустимый путь файла")
        return target

    async def update_code(self, script_id: int, code: str) -> LuaScript:
        """Перезаписать тело существующего скрипта."""
        row = await self.by_id(script_id)
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "скрипт не найден")
        target = self._safe_target(row.filename)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(code, encoding="utf-8")
        row.sha256 = hashlib.sha256(code.encode()).hexdigest()
        await self.s.flush()
        return row

    async def delete(self, script_id: int) -> None:
        """Удалить запись скрипта и его файл."""
        row = await self.by_id(script_id)
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "скрипт не найден")
        target = self._safe_target(row.filename)
        if target.exists():
            target.unlink()
        await self.s.delete(row)
        await self.s.flush()


def _scripts_dir(request: Request) -> str:
    cfg: AppConfig = request.app.state.settings
    return cfg.LUA_SCRIPTS_DIR


def get_service_mngr(session: AsyncSession = Depends(get_db_session)) -> ServiceMngr:
    return ServiceMngr(session)


def get_catalog_mngr(session: AsyncSession = Depends(get_db_session)) -> CatalogMngr:
    return CatalogMngr(session)


def get_script_mngr(
    request: Request, session: AsyncSession = Depends(get_db_session)
) -> ScriptMngr:
    return ScriptMngr(session, _scripts_dir(request))


def get_storage(request: Request) -> StorageSvc:
    return StorageSvc(request.app.state.settings)


__all__ = [
    "ServiceMngr",
    "CatalogMngr",
    "ScriptMngr",
    "get_service_mngr",
    "get_catalog_mngr",
    "get_script_mngr",
    "get_storage",
]
