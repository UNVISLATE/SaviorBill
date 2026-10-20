"""Админ: глобальное управление пулом цифровых ключей (/api/v1/admin/service-keys)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select

from dependencies.catalog import (
    ServiceKeysMngr,
    ServiceMngr,
    get_service_mngr,
    get_servicekeys_mngr,
)
from dependencies.rbac import require_perm
from models.service_catalogs import ServiceCatalogsModel
from models.service import ServiceModel
from models.service_keys import ServiceKeysModel
from schemas.page import Page
from pydantic import BaseModel, Field
from dependencies.settings import SystemSettingsMngr, get_settings_mngr
from dependencies.triggers import TriggerDispatcher, get_dispatcher
from lifecycle.triggers.stock import check_and_fire_key_stock_triggers
from schemas.service_keys import (
    GlobalServiceKeysImportIn,
    ServiceKeyGlobalOut,
    ServiceKeyRevealOut,
    ServiceKeysImportOut,
    ServiceKeysOverviewOut,
    ServiceStockItem,
)
from utils.pagination import (
    PageParams,
    apply_sort,
    page_params,
    paginate_rows,
    sort_param,
)

router = APIRouter()

_KEY_SORT_FIELDS = {"id", "created_at", "is_used", "used_at"}


@router.get(
    "",
    response_model=Page[ServiceKeyGlobalOut],
    dependencies=[Depends(require_perm("services.keys.read"))],
    summary="Global service keys",
)
async def list_global_keys(
    service_id: int | None = None,
    is_used: bool | None = None,
    order_id: int | None = None,
    pp: PageParams = Depends(page_params),
    sort: str | None = Depends(sort_param),
    mngr: ServiceKeysMngr = Depends(get_servicekeys_mngr),
) -> Page[ServiceKeyGlobalOut]:
    stmt = (
        select(
            ServiceKeysModel,
            ServiceModel.name.label("service_name"),
            ServiceModel.slug.label("service_slug"),
        )
        .join(ServiceModel, ServiceKeysModel.service_id == ServiceModel.id)
    )

    if service_id is not None:
        stmt = stmt.where(ServiceKeysModel.service_id == service_id)
    if is_used is not None:
        stmt = stmt.where(ServiceKeysModel.is_used == is_used)
    if order_id is not None:
        stmt = stmt.where(ServiceKeysModel.order_id == order_id)

    stmt = apply_sort(stmt, ServiceKeysModel, sort, _KEY_SORT_FIELDS)
    if sort is None:
        stmt = stmt.order_by(ServiceKeysModel.created_at.desc())

    def _transform(row) -> ServiceKeyGlobalOut:  # noqa: ANN001
        # row can be a Row tuple (ServiceKeysModel, service_name, service_slug)
        key_model = row[0]
        s_name = row[1]
        s_slug = row[2]
        return ServiceKeyGlobalOut(
            id=key_model.id,
            service_id=key_model.service_id,
            service_name=s_name,
            service_slug=s_slug,
            is_used=key_model.is_used,
            used_at=key_model.used_at,
            order_id=key_model.order_id,
            created_at=key_model.created_at,
            value="***",
        )

    items, total, has_more = await paginate_rows(
        mngr.s, stmt, _transform, limit=pp.limit, offset=pp.offset
    )
    return Page(
        items=items, total=total, limit=pp.limit, offset=pp.offset, has_more=has_more
    )


@router.get(
    "/overview",
    response_model=ServiceKeysOverviewOut,
    dependencies=[Depends(require_perm("services.keys.read"))],
    summary="Keys stock overview across all services",
)
async def get_keys_overview(
    threshold: int | None = None,
    mngr: ServiceKeysMngr = Depends(get_servicekeys_mngr),
    settings: SystemSettingsMngr = Depends(get_settings_mngr),
) -> ServiceKeysOverviewOut:
    if threshold is None or threshold <= 0:
        threshold = await settings.get_int("service.keys_low_threshold", 5) or 5
    # Запрашиваем все услуги с типом выдачи key
    services_stmt = (
        select(
            ServiceModel.id,
            ServiceModel.name,
            ServiceModel.slug,
            ServiceModel.catalog_id,
            ServiceCatalogsModel.name.label("catalog_name"),
            ServiceModel.price,
            ServiceModel.currency,
            ServiceModel.is_active,
        )
        .outerjoin(ServiceCatalogsModel, ServiceModel.catalog_id == ServiceCatalogsModel.id)
        .where(ServiceModel.delivery == "key")
        .order_by(ServiceModel.name)
    )
    services_res = (await mngr.s.execute(services_stmt)).all()

    # Группировка ключей по service_id и is_used
    counts_stmt = (
        select(
            ServiceKeysModel.service_id,
            ServiceKeysModel.is_used,
            func.count(ServiceKeysModel.id).label("cnt"),
        )
        .group_by(ServiceKeysModel.service_id, ServiceKeysModel.is_used)
    )
    counts_res = (await mngr.s.execute(counts_stmt)).all()

    counts_map: dict[int, dict[bool, int]] = {}
    for sid, is_used, cnt in counts_res:
        if sid not in counts_map:
            counts_map[sid] = {False: 0, True: 0}
        counts_map[sid][bool(is_used)] = int(cnt or 0)

    items: list[ServiceStockItem] = []
    total_avail = 0
    total_used = 0
    out_of_stock_count = 0
    low_stock_count = 0

    for s in services_res:
        sid = s.id
        sc = counts_map.get(sid, {False: 0, True: 0})
        avail = sc.get(False, 0)
        used = sc.get(True, 0)
        total = avail + used

        total_avail += avail
        total_used += used

        if avail == 0:
            status_str = "out_of_stock"
            out_of_stock_count += 1
        elif avail < threshold:
            status_str = "low"
            low_stock_count += 1
        else:
            status_str = "ok"

        items.append(
            ServiceStockItem(
                service_id=sid,
                service_name=s.name,
                service_slug=s.slug,
                catalog_id=s.catalog_id,
                catalog_name=s.catalog_name,
                price=s.price,
                currency=s.currency,
                is_active=s.is_active,
                available_keys=avail,
                used_keys=used,
                total_keys=total,
                stock_status=status_str,
            )
        )

    return ServiceKeysOverviewOut(
        total_available=total_avail,
        total_used=total_used,
        total_keys=total_avail + total_used,
        out_of_stock_count=out_of_stock_count,
        low_stock_count=low_stock_count,
        threshold=threshold,
        items=items,
    )


@router.post(
    "/import",
    response_model=ServiceKeysImportOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_perm("services.keys.create"))],
    summary="Import keys globally",
)
async def import_keys_globally(
    body: GlobalServiceKeysImportIn,
    svc_mngr: ServiceMngr = Depends(get_service_mngr),
    mngr: ServiceKeysMngr = Depends(get_servicekeys_mngr),
) -> ServiceKeysImportOut:
    svc = await svc_mngr.by_id(body.service_id)
    if svc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "service not found")
    created, skipped = await mngr.create_batch(body.service_id, body.values)
    await mngr.s.commit()
    from schemas.service_keys import ServiceKeyOut
    return ServiceKeysImportOut(
        added=len(created),
        skipped=skipped,
        keys=[ServiceKeyOut.from_model(k) for k in created],
    )


@router.get(
    "/{key_id}/reveal",
    response_model=ServiceKeyRevealOut,
    dependencies=[Depends(require_perm("ownersec.servicekeys.read"))],
    summary="Reveal key globally",
)
async def reveal_key_globally(
    key_id: int,
    mngr: ServiceKeysMngr = Depends(get_servicekeys_mngr),
) -> ServiceKeyRevealOut:
    key = await mngr.by_id(key_id)
    if key is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "key not found")
    return ServiceKeyRevealOut(id=key.id, value=mngr.reveal(key))


class KeysThresholdIn(BaseModel):
    threshold: int = Field(ge=1, le=10000, description="Новый порог малого остатка ключей")


@router.post(
    "/threshold",
    dependencies=[Depends(require_perm("settings.edit"))],
    summary="Update low keys threshold in settings",
)
async def update_keys_threshold(
    body: KeysThresholdIn,
    settings: SystemSettingsMngr = Depends(get_settings_mngr),
) -> dict:
    await settings.set("service.keys_low_threshold", str(body.threshold))
    return {"ok": True, "threshold": body.threshold}


@router.delete(
    "/{key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_perm("services.keys.delete"))],
    summary="Delete key globally",
)
async def delete_key_globally(
    key_id: int,
    mngr: ServiceKeysMngr = Depends(get_servicekeys_mngr),
    dispatcher: TriggerDispatcher = Depends(get_dispatcher),
) -> None:
    key = await mngr.by_id(key_id)
    if key is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "key not found")
    service_id = key.service_id
    await mngr.delete(key_id)
    await mngr.s.commit()
    service = await mngr.s.get(ServiceModel, service_id)
    if service is not None:
        await check_and_fire_key_stock_triggers(mngr.s, service, dispatcher)


__all__ = ["router"]
