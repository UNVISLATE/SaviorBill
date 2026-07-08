"""Публичный каталог: услуги и дерево каталогов."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from dependencies.catalog import (
    ServiceCatalogsMngr,
    ServiceKeysMngr,
    ServiceMngr,
    get_catalog_mngr,
    get_service_mngr,
    get_servicekeys_mngr,
)
from enums import Delivery
from schemas.catalog import CatalogResponse
from schemas.page import Page
from schemas.service import Service
from utils.pagination import PageParams, page_params, paginate

router = APIRouter(prefix="/api/v1/catalog", tags=["catalog"])


async def _with_stock(svc: Service, service_id: int, keys_mngr: ServiceKeysMngr) -> Service:
    """Проставить ``out_of_stock`` для delivery=key (вычисляемый статус, §4.2)."""
    if svc.delivery != Delivery.KEY:
        return svc
    available = await keys_mngr.count_available(service_id)
    return svc.with_stock(available == 0)


@router.get(
    "/catalogs", response_model=list[CatalogResponse], summary="Дерево каталогов"
)
async def list_catalogs(
    mngr: ServiceCatalogsMngr = Depends(get_catalog_mngr),
) -> list[CatalogResponse]:
    """Все активные каталоги (плоско; иерархия — через parent_id)."""
    rows = await mngr.list_all()
    return [CatalogResponse.from_model(c) for c in rows if c.is_active]


@router.get("/services", response_model=Page[Service], summary="Список услуг")
async def list_services(
    catalog_id: int | None = Query(default=None, description="фильтр по каталогу"),
    pp: PageParams = Depends(page_params),
    mngr: ServiceMngr = Depends(get_service_mngr),
    keys_mngr: ServiceKeysMngr = Depends(get_servicekeys_mngr),
) -> Page[Service]:
    """Активные услуги каталога (опц. в рамках одного каталога), постранично."""
    items, total, has_more = await paginate(
        mngr.s,
        mngr.stmt_active(catalog_id),
        Service.from_model,
        limit=pp.limit,
        offset=pp.offset,
    )
    items = [await _with_stock(svc, svc.id, keys_mngr) for svc in items]
    return Page(
        items=items, total=total, limit=pp.limit, offset=pp.offset, has_more=has_more
    )


@router.get("/services/{service_id}", response_model=Service, summary="Карточка услуги")
async def get_service(
    service_id: int,
    mngr: ServiceMngr = Depends(get_service_mngr),
    keys_mngr: ServiceKeysMngr = Depends(get_servicekeys_mngr),
) -> Service:
    """Получить активную услугу по идентификатору."""
    svc = await mngr.get_active(service_id)
    return await _with_stock(Service.from_model(svc), service_id, keys_mngr)


__all__ = ["router"]

