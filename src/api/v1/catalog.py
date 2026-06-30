"""Публичный каталог: услуги и дерево каталогов."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from dependencies.catalog import (
    ServiceCatalogsMngr,
    ServiceMngr,
    get_catalog_mngr,
    get_service_mngr,
)
from schemas.catalog import CatalogResponse
from schemas.service import Service

router = APIRouter(prefix="/api/v1/catalog", tags=["catalog"])


@router.get(
    "/catalogs", response_model=list[CatalogResponse], summary="Дерево каталогов"
)
async def list_catalogs(
    mngr: ServiceCatalogsMngr = Depends(get_catalog_mngr),
) -> list[CatalogResponse]:
    """Все активные каталоги (плоско; иерархия — через parent_id)."""
    rows = await mngr.list_all()
    return [CatalogResponse.from_model(c) for c in rows if c.is_active]


@router.get("/services", response_model=list[Service], summary="Список услуг")
async def list_services(
    catalog_id: int | None = Query(default=None, description="фильтр по каталогу"),
    mngr: ServiceMngr = Depends(get_service_mngr),
) -> list[Service]:
    """Активные услуги каталога (опц. в рамках одного каталога)."""
    rows = await mngr.list_active(catalog_id)
    return [Service.from_model(s) for s in rows]


@router.get("/services/{service_id}", response_model=Service, summary="Карточка услуги")
async def get_service(
    service_id: int, mngr: ServiceMngr = Depends(get_service_mngr)
) -> Service:
    """Получить активную услугу по идентификатору."""
    svc = await mngr.get_active(service_id)
    return Service.from_model(svc)


__all__ = ["router"]
