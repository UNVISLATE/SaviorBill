"""Админ: управление услугами (/api/v1/admin/services)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from dependencies.catalog import (
    ServiceAttachmentMngr,
    ServiceMngr,
    get_attachment_mngr,
    get_service_mngr,
)
from dependencies.rbac import require_perm
from schemas.media import Attachment, AttachmentIn
from schemas.page import Page
from schemas.service import ServiceAdmin, ServiceCreate, ServicePatch
from utils.pagination import PageParams, page_params, paginate
from utils.apidoc import with_fields

router = APIRouter()


@router.get(
    "/services",
    response_model=Page[ServiceAdmin],
    dependencies=[Depends(require_perm("services.read"))],
    summary="Список услуг (все)",
)
async def list_services(
    pp: PageParams = Depends(page_params),
    mngr: ServiceMngr = Depends(get_service_mngr),
) -> Page[ServiceAdmin]:
    items, total, has_more = await paginate(
        mngr.s,
        mngr.stmt_all(),
        ServiceAdmin.from_model,
        limit=pp.limit,
        offset=pp.offset,
    )
    return Page(
        items=items, total=total, limit=pp.limit, offset=pp.offset, has_more=has_more
    )


@router.post(
    "/services",
    response_model=ServiceAdmin,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_perm("services.create"))],
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
    svc, warnings = await mngr.update(service_id, body.model_dump(exclude_unset=True))
    await mngr.s.commit()
    return ServiceAdmin.from_model(svc, warnings=warnings)


@router.get(
    "/services/{service_id}/attachments",
    response_model=list[Attachment],
    dependencies=[Depends(require_perm("services.attachments.read"))],
    summary="Вложения товара",
)
async def list_attachments(
    service_id: int,
    mngr: ServiceAttachmentMngr = Depends(get_attachment_mngr),
) -> list[Attachment]:
    rows = await mngr.list_by_service(service_id)
    return [Attachment.from_model(a) for a in rows]


@router.post(
    "/services/{service_id}/attachments",
    response_model=Attachment,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_perm("services.attachments.create"))],
    summary="Добавить вложение товара",
    description=with_fields(
        "Привязывает загруженное медиа к товару с тегом и позицией.",
        AttachmentIn,
    ),
)
async def add_attachment(
    service_id: int,
    body: AttachmentIn,
    svc_mngr: ServiceMngr = Depends(get_service_mngr),
    mngr: ServiceAttachmentMngr = Depends(get_attachment_mngr),
) -> Attachment:
    if await svc_mngr.by_id(service_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "услуга не найдена")
    att = await mngr.add(
        service_id, body.media_id, tag=body.tag, position=body.position
    )
    await mngr.s.commit()
    await mngr.s.refresh(att)
    return Attachment.from_model(att)


@router.delete(
    "/services/{service_id}/attachments/{att_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_perm("services.attachments.delete"))],
    summary="Удалить вложение товара",
)
async def remove_attachment(
    service_id: int,
    att_id: int,
    mngr: ServiceAttachmentMngr = Depends(get_attachment_mngr),
) -> None:
    await mngr.remove(att_id)
    await mngr.s.commit()


__all__ = ["router"]
