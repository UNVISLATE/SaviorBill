"""Админ: пул цифровых ключей услуги (/api/v1/admin/services/{id}/keys).

Разделение прав на чтение (см. IMPLEMENTATION_PLAN.md §3):

- ``services.keys.read`` — список/остаток; значение ключа всегда замаскировано.
- ``ownersec.servicekeys.read`` — отдельное, не наследуемое от обычных
  ``*.read``/``admin: {"*": ...}`` право, только оно раскрывает расшифрованное
  значение конкретного ключа.
- ``services.keys.create`` — массовый импорт.
- ``services.keys.delete`` — удаление ключа.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from dependencies.catalog import (
    ServiceKeysMngr,
    ServiceMngr,
    get_service_mngr,
    get_servicekeys_mngr,
)
from dependencies.rbac import require_perm
from schemas.page import Page
from schemas.service_keys import (
    ServiceKeyOut,
    ServiceKeyRevealOut,
    ServiceKeysImportIn,
    ServiceKeysImportOut,
    ServiceStockOut,
)
from utils.apidoc import with_fields
from utils.pagination import PageParams, page_params, paginate
from sqlalchemy import select

router = APIRouter()


async def _get_service_or_404(service_id: int, svc_mngr: ServiceMngr):
    service = await svc_mngr.by_id(service_id)
    if service is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "услуга не найдена")
    return service


@router.get(
    "/services/{service_id}/keys",
    response_model=Page[ServiceKeyOut],
    dependencies=[Depends(require_perm("services.keys.read"))],
    summary="Список ключей услуги (значения замаскированы)",
)
async def list_keys(
    service_id: int,
    pp: PageParams = Depends(page_params),
    svc_mngr: ServiceMngr = Depends(get_service_mngr),
    mngr: ServiceKeysMngr = Depends(get_servicekeys_mngr),
) -> Page[ServiceKeyOut]:
    from models.service_keys import ServiceKeysModel

    await _get_service_or_404(service_id, svc_mngr)
    stmt = (
        select(ServiceKeysModel)
        .where(ServiceKeysModel.service_id == service_id)
        .order_by(ServiceKeysModel.id)
    )
    items, total, has_more = await paginate(
        mngr.s, stmt, ServiceKeyOut.from_model, limit=pp.limit, offset=pp.offset
    )
    return Page(
        items=items, total=total, limit=pp.limit, offset=pp.offset, has_more=has_more
    )


@router.get(
    "/services/{service_id}/keys/stock",
    response_model=ServiceStockOut,
    dependencies=[Depends(require_perm("services.keys.read"))],
    summary="Остаток ключей (вычисляемый, не колонка БД)",
)
async def keys_stock(
    service_id: int,
    svc_mngr: ServiceMngr = Depends(get_service_mngr),
    mngr: ServiceKeysMngr = Depends(get_servicekeys_mngr),
) -> ServiceStockOut:
    await _get_service_or_404(service_id, svc_mngr)
    available = await mngr.count_available(service_id)
    return ServiceStockOut.build(service_id, available)


@router.get(
    "/services/{service_id}/keys/{key_id}/reveal",
    response_model=ServiceKeyRevealOut,
    dependencies=[Depends(require_perm("ownersec.servicekeys.read"))],
    summary="Раскрыть значение ключа (отдельное право)",
    description=(
        "Возвращает расшифрованное значение ключа. Требует отдельного права "
        "`ownersec.servicekeys.read`, не входящего в обычное `services.*` — "
        "чтобы секрет нельзя было случайно раскрыть выдачей общего read-доступа."
    ),
)
async def reveal_key(
    service_id: int,
    key_id: int,
    svc_mngr: ServiceMngr = Depends(get_service_mngr),
    mngr: ServiceKeysMngr = Depends(get_servicekeys_mngr),
) -> ServiceKeyRevealOut:
    await _get_service_or_404(service_id, svc_mngr)
    key = await mngr.by_id(key_id)
    if key is None or key.service_id != service_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ключ не найден")
    return ServiceKeyRevealOut(id=key.id, value=mngr.reveal(key))


@router.post(
    "/services/{service_id}/keys/import",
    response_model=ServiceKeysImportOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_perm("services.keys.create"))],
    summary="Массовый импорт ключей",
    description=with_fields(
        "Принимает готовый JSON-список открытых значений (разбор свободного "
        "текста — задача фронтенда, не бэкенда). Дедупликация — только в "
        "пределах присланного списка.",
        ServiceKeysImportIn,
    ),
)
async def import_keys(
    service_id: int,
    body: ServiceKeysImportIn,
    svc_mngr: ServiceMngr = Depends(get_service_mngr),
    mngr: ServiceKeysMngr = Depends(get_servicekeys_mngr),
) -> ServiceKeysImportOut:
    await _get_service_or_404(service_id, svc_mngr)
    created, skipped = await mngr.create_batch(service_id, body.values)
    await mngr.s.commit()
    return ServiceKeysImportOut(
        added=len(created),
        skipped=skipped,
        keys=[ServiceKeyOut.from_model(k) for k in created],
    )


@router.delete(
    "/services/{service_id}/keys/{key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_perm("services.keys.delete"))],
    summary="Удалить ключ из пула",
)
async def delete_key(
    service_id: int,
    key_id: int,
    svc_mngr: ServiceMngr = Depends(get_service_mngr),
    mngr: ServiceKeysMngr = Depends(get_servicekeys_mngr),
) -> None:
    await _get_service_or_404(service_id, svc_mngr)
    key = await mngr.by_id(key_id)
    if key is None or key.service_id != service_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ключ не найден")
    await mngr.delete(key_id)
    await mngr.s.commit()


__all__ = ["router"]
