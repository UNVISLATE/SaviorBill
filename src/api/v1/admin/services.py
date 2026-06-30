"""Админ: управление услугами (/api/v1/admin/services)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from dependencies.catalog import ServiceMngr, get_service_mngr
from dependencies.rbac import require_perm
from schemas.service import ServiceAdmin, ServiceCreate, ServicePatch

router = APIRouter()


@router.get(
    "/services",
    response_model=list[ServiceAdmin],
    dependencies=[Depends(require_perm("services.read"))],
    summary="Список услуг (все)",
)
async def list_services(
    mngr: ServiceMngr = Depends(get_service_mngr),
) -> list[ServiceAdmin]:
    rows = await mngr.list_all()
    return [ServiceAdmin.from_model(r) for r in rows]


@router.post(
    "/services",
    response_model=ServiceAdmin,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_perm("services.edit"))],
    summary="Создать услугу",
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
