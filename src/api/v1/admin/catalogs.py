"""Админ: управление каталогами услуг (/api/v1/admin/catalogs)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from dependencies.catalog import ServiceCatalogsMngr, get_catalog_mngr
from dependencies.rbac import require_perm
from schemas.catalog import CatalogRequest, CatalogResponse, CatalogPatch

router = APIRouter()


@router.get(
    "",
    response_model=list[CatalogResponse],
    dependencies=[Depends(require_perm("catalogs.read"))],
    summary="Catalogs",
)
async def list_catalogs(
    mngr: ServiceCatalogsMngr = Depends(get_catalog_mngr),
) -> list[CatalogResponse]:
    rows = await mngr.list_all()
    return [CatalogResponse.from_model(r) for r in rows]


@router.post(
    "",
    response_model=CatalogResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_perm("catalogs.create"))],
    summary="Create catalog",
    description="Create a service catalog.",
)
async def create_catalog(
    body: CatalogRequest, mngr: ServiceCatalogsMngr = Depends(get_catalog_mngr)
) -> CatalogResponse:
    cat = await mngr.create(body.model_dump())
    await mngr.s.commit()
    return CatalogResponse.from_model(cat)


@router.patch(
    "/{catalog_id}",
    response_model=CatalogResponse,
    dependencies=[Depends(require_perm("catalogs.edit"))],
    summary="Update catalog",
    description="Update a service catalog.",
)
async def update_catalog(
    catalog_id: int,
    body: CatalogPatch,
    mngr: ServiceCatalogsMngr = Depends(get_catalog_mngr),
) -> CatalogResponse:
    cat = await mngr.update(catalog_id, body.model_dump(exclude_unset=True))
    await mngr.s.commit()
    return CatalogResponse.from_model(cat)


@router.delete(
    "/{catalog_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_perm("catalogs.delete"))],
    summary="Delete catalog",
)
async def delete_catalog(
    catalog_id: int, mngr: ServiceCatalogsMngr = Depends(get_catalog_mngr)
) -> None:
    await mngr.delete(catalog_id)
    await mngr.s.commit()


__all__ = ["router"]
