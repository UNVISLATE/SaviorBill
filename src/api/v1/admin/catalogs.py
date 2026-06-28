"""Админ: управление каталогами услуг (/api/v1/admin/catalogs)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from dependencies.catalog import CatalogMngr, get_catalog_mngr
from dependencies.rbac import require_perm
from schemas.catalog import CatalogIn, CatalogOut, CatalogPatch

router = APIRouter()


@router.get(
    "/catalogs",
    response_model=list[CatalogOut],
    dependencies=[Depends(require_perm("catalogs.read"))],
    summary="Список каталогов",
)
async def list_catalogs(
    mngr: CatalogMngr = Depends(get_catalog_mngr),
) -> list[CatalogOut]:
    return await mngr.list_all()


@router.post(
    "/catalogs",
    response_model=CatalogOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_perm("catalogs.edit"))],
    summary="Создать каталог",
)
async def create_catalog(
    body: CatalogIn, mngr: CatalogMngr = Depends(get_catalog_mngr)
) -> CatalogOut:
    cat = await mngr.create(body.model_dump())
    await mngr.s.commit()
    return cat


@router.patch(
    "/catalogs/{catalog_id}",
    response_model=CatalogOut,
    dependencies=[Depends(require_perm("catalogs.edit"))],
    summary="Изменить каталог",
)
async def update_catalog(
    catalog_id: int,
    body: CatalogPatch,
    mngr: CatalogMngr = Depends(get_catalog_mngr),
) -> CatalogOut:
    cat = await mngr.update(catalog_id, body.model_dump(exclude_unset=True))
    await mngr.s.commit()
    return cat


@router.delete(
    "/catalogs/{catalog_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_perm("catalogs.edit"))],
    summary="Удалить каталог",
)
async def delete_catalog(
    catalog_id: int, mngr: CatalogMngr = Depends(get_catalog_mngr)
) -> None:
    await mngr.delete(catalog_id)
    await mngr.s.commit()


__all__ = ["router"]
