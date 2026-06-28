"""Админ: управление услугами (/api/v1/admin/services)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from dependencies.catalog import ServiceMngr, get_service_mngr
from dependencies.rbac import require_perm
from schemas.catalog import ServiceAdminOut, ServiceCreate, ServicePatch

router = APIRouter()


@router.get(
    "/services",
    response_model=list[ServiceAdminOut],
    dependencies=[Depends(require_perm("services.read"))],
    summary="Список услуг (все)",
)
async def list_services(
    mngr: ServiceMngr = Depends(get_service_mngr),
) -> list[ServiceAdminOut]:
    return await mngr.list_all()


@router.post(
    "/services",
    response_model=ServiceAdminOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_perm("services.edit"))],
    summary="Создать услугу",
)
async def create_service(
    body: ServiceCreate, mngr: ServiceMngr = Depends(get_service_mngr)
) -> ServiceAdminOut:
    svc = await mngr.create(body.model_dump())
    await mngr.s.commit()
    return svc


@router.patch(
    "/services/{service_id}",
    response_model=ServiceAdminOut,
    dependencies=[Depends(require_perm("services.edit"))],
    summary="Изменить услугу",
)
async def update_service(
    service_id: int,
    body: ServicePatch,
    mngr: ServiceMngr = Depends(get_service_mngr),
) -> ServiceAdminOut:
    svc = await mngr.update(service_id, body.model_dump(exclude_unset=True))
    await mngr.s.commit()
    return svc


__all__ = ["router"]
