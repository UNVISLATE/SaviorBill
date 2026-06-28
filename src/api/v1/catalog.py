"""Публичный каталог: услуги и дерево каталогов."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from dependencies.catalog import (
    CatalogMngr,
    ServiceMngr,
    get_catalog_mngr,
    get_service_mngr,
)
from schemas.catalog import CatalogOut, ServiceOut

router = APIRouter(prefix="/api/v1/catalog", tags=["catalog"])


@router.get(
    "/catalogs", response_model=list[CatalogOut], summary="Дерево каталогов"
)
async def list_catalogs(
    mngr: CatalogMngr = Depends(get_catalog_mngr),
) -> list[CatalogOut]:
    """Все активные каталоги (плоско; иерархия — через parent_id)."""
    return [c for c in await mngr.list_all() if c.is_active]


@router.get("/services", response_model=list[ServiceOut], summary="Список услуг")
async def list_services(
    catalog_id: int | None = Query(default=None, description="фильтр по каталогу"),
    mngr: ServiceMngr = Depends(get_service_mngr),
) -> list[ServiceOut]:
    """Активные услуги каталога (опц. в рамках одного каталога)."""
    return await mngr.list_active(catalog_id)


@router.get(
    "/services/{service_id}", response_model=ServiceOut, summary="Карточка услуги"
)
async def get_service(
    service_id: int, mngr: ServiceMngr = Depends(get_service_mngr)
) -> ServiceOut:
    """Получить активную услугу по идентификатору."""
    return await mngr.get_active(service_id)


__all__ = ["router"]
