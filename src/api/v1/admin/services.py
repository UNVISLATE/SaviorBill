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
from models.service import ServiceModel
from schemas.media import Attachment, AttachmentIn
from schemas.page import Page
from schemas.service import ServiceAdmin, ServiceCreate, ServicePatch
from utils.pagination import (
    PageParams,
    apply_sort,
    page_params,
    paginate_search,
    q_param,
    sort_param,
)

router = APIRouter()

_SORT_FIELDS = {"id", "name", "price", "is_active", "created_at", "catalog_id"}


@router.get(
    "",
    response_model=Page[ServiceAdmin],
    dependencies=[Depends(require_perm("services.read"))],
    summary="Services",
    description="`q` searches name/description (fuzzy fallback on name); "
    f"`sort` accepts {'/'.join(sorted(_SORT_FIELDS))}.",
)
async def list_services(
    pp: PageParams = Depends(page_params),
    q: str | None = Depends(q_param),
    sort: str | None = Depends(sort_param),
    mngr: ServiceMngr = Depends(get_service_mngr),
) -> Page[ServiceAdmin]:
    stmt = apply_sort(mngr.stmt_all(), ServiceModel, sort, _SORT_FIELDS)
    items, total, has_more = await paginate_search(
        mngr.s,
        stmt,
        ServiceModel,
        ServiceAdmin.from_model,
        limit=pp.limit,
        offset=pp.offset,
        q=q,
        search_fields=("name", "description"),
        fuzzy_fields=("name",),
    )
    return Page(
        items=items, total=total, limit=pp.limit, offset=pp.offset, has_more=has_more
    )


@router.post(
    "",
    response_model=ServiceAdmin,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_perm("services.create"))],
    summary="Create service",
    description="Create a service.",
)
async def create_service(
    body: ServiceCreate, mngr: ServiceMngr = Depends(get_service_mngr)
) -> ServiceAdmin:
    svc = await mngr.create(body.model_dump())
    await mngr.s.commit()
    return ServiceAdmin.from_model(svc)


@router.patch(
    "/{service_id}",
    response_model=ServiceAdmin,
    dependencies=[Depends(require_perm("services.edit"))],
    summary="Update service",
    description="Update a service.",
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
    "/{service_id}/attachments",
    response_model=list[Attachment],
    dependencies=[Depends(require_perm("services.attachments.read"))],
    summary="Service attachments",
)
async def list_attachments(
    service_id: int,
    mngr: ServiceAttachmentMngr = Depends(get_attachment_mngr),
) -> list[Attachment]:
    rows = await mngr.list_by_service(service_id)
    return [Attachment.from_model(a) for a in rows]


@router.post(
    "/{service_id}/attachments",
    response_model=Attachment,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_perm("services.attachments.create"))],
    summary="Add attachment",
    description="Attach uploaded media to a service.",
)
async def add_attachment(
    service_id: int,
    body: AttachmentIn,
    svc_mngr: ServiceMngr = Depends(get_service_mngr),
    mngr: ServiceAttachmentMngr = Depends(get_attachment_mngr),
) -> Attachment:
    if await svc_mngr.by_id(service_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "service not found")
    att = await mngr.add(
        service_id, body.media_id, tag=body.tag, position=body.position
    )
    await mngr.s.commit()
    await mngr.s.refresh(att)
    return Attachment.from_model(att)


@router.delete(
    "/{service_id}/attachments/{att_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_perm("services.attachments.delete"))],
    summary="Delete attachment",
)
async def remove_attachment(
    service_id: int,
    att_id: int,
    mngr: ServiceAttachmentMngr = Depends(get_attachment_mngr),
) -> None:
    await mngr.remove(att_id)
    await mngr.s.commit()


__all__ = ["router"]
