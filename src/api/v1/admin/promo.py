"""Админ: каталоги промокодов и выпуск кодов (/api/v1/admin/promo)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from dependencies.promo import (
    PromoCatalogsMngr,
    PromoCodesMngr,
    get_promo_catalog_mngr,
    get_promo_mngr,
)
from dependencies.rbac import require_perm
from schemas.promo import (
    PromoCatalog,
    PromoCatalogCreate,
    PromoCatalogPatch,
    PromoCode,
    PromoCodeBatch,
)

router = APIRouter()


@router.get(
    "/promo/catalogs",
    response_model=list[PromoCatalog],
    dependencies=[Depends(require_perm("promo.read"))],
    summary="Список каталогов промокодов",
)
async def list_catalogs(
    mngr: PromoCatalogsMngr = Depends(get_promo_catalog_mngr),
) -> list[PromoCatalog]:
    rows = await mngr.list_all()
    return [PromoCatalog.from_model(r) for r in rows]


@router.post(
    "/promo/catalogs",
    response_model=PromoCatalog,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_perm("promo.edit"))],
    summary="Создать каталог промокодов",
)
async def create_catalog(
    body: PromoCatalogCreate,
    mngr: PromoCatalogsMngr = Depends(get_promo_catalog_mngr),
) -> PromoCatalog:
    cat = await mngr.create(body.model_dump())
    await mngr.s.commit()
    return PromoCatalog.from_model(cat)


@router.patch(
    "/promo/catalogs/{catalog_id}",
    response_model=PromoCatalog,
    dependencies=[Depends(require_perm("promo.edit"))],
    summary="Изменить каталог промокодов",
)
async def update_catalog(
    catalog_id: int,
    body: PromoCatalogPatch,
    mngr: PromoCatalogsMngr = Depends(get_promo_catalog_mngr),
) -> PromoCatalog:
    cat = await mngr.update(catalog_id, body.model_dump(exclude_unset=True))
    if cat is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "каталог не найден")
    await mngr.s.commit()
    return PromoCatalog.from_model(cat)


@router.delete(
    "/promo/catalogs/{catalog_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_perm("promo.edit"))],
    summary="Удалить каталог промокодов",
)
async def delete_catalog(
    catalog_id: int,
    mngr: PromoCatalogsMngr = Depends(get_promo_catalog_mngr),
) -> None:
    await mngr.delete(catalog_id)
    await mngr.s.commit()


@router.get(
    "/promo/catalogs/{catalog_id}/codes",
    response_model=list[PromoCode],
    dependencies=[Depends(require_perm("promo.read"))],
    summary="Коды каталога",
)
async def list_codes(
    catalog_id: int,
    mngr: PromoCodesMngr = Depends(get_promo_mngr),
) -> list[PromoCode]:
    rows = await mngr.list_for(catalog_id)
    return [PromoCode.from_model(r) for r in rows]


@router.post(
    "/promo/codes",
    response_model=list[PromoCode],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_perm("promo.edit"))],
    summary="Выпустить пачку кодов",
)
async def create_codes(
    body: PromoCodeBatch,
    mngr: PromoCodesMngr = Depends(get_promo_mngr),
) -> list[PromoCode]:
    if not body.codes and body.count <= 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "укажите codes или count > 0")
    rows = await mngr.create_batch(
        body.catalog_id,
        codes=body.codes,
        count=body.count,
        prefix=body.prefix,
        max_uses=body.max_uses,
        valid_to=body.valid_to,
    )
    await mngr.s.commit()
    return [PromoCode.from_model(r) for r in rows]


__all__ = ["router"]
