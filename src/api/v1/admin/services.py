"""Админ: управление услугами (/api/v1/admin/services)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status

from dependencies.catalog import ServiceMngr, get_service_mngr
from dependencies.rbac import require_perm
from schemas.page import Page
from schemas.service import ServiceAdmin, ServiceCreate, ServicePatch
from utils.pagination import paginate
from utils.apidoc import with_fields

router = APIRouter()


@router.get(
    "/services",
    response_model=Page[ServiceAdmin],
    dependencies=[Depends(require_perm("services.read"))],
    summary="Список услуг (все)",
)
async def list_services(
    limit: int = Query(50, ge=1, le=200, description="Размер страницы (опционально)"),
    offset: int = Query(0, ge=0, description="Смещение выборки (опционально)"),
    mngr: ServiceMngr = Depends(get_service_mngr),
) -> Page[ServiceAdmin]:
    items, total = await paginate(
        mngr.s, mngr.stmt_all(), ServiceAdmin.from_model, limit=limit, offset=offset
    )
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.post(
    "/services",
    response_model=ServiceAdmin,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_perm("services.edit"))],
    summary="Создать услугу",
    description=with_fields(
        "Создаёт услугу каталога.",
        ServiceCreate,
    ),
)
async def create_service(
    body: ServiceCreate, mngr: ServiceMngr = Depends(get_service_mngr)
) -> ServiceAdmin:
    svc = await mngr.create(body.model_dump())
    await mngr.s.commit()
    return ServiceAdmin.from_model(svc)


@router.patch(
    "/services/{service_id}",
    response_model=ServiceAdmin,
    dependencies=[Depends(require_perm("services.edit"))],
    summary="Изменить услугу",
    description=with_fields(
        "Частично обновляет услугу — передаются только изменяемые поля.",
        ServicePatch,
    ),
)
async def update_service(
    service_id: int,
    body: ServicePatch,
    mngr: ServiceMngr = Depends(get_service_mngr),
) -> ServiceAdmin:
    svc = await mngr.update(service_id, body.model_dump(exclude_unset=True))
    await mngr.s.commit()
    return ServiceAdmin.from_model(svc)


__all__ = ["router"]
