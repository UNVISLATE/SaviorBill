"""Админ: управление email-шаблонами (/api/v1/admin/email)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from dependencies.email import get_email_templates_mngr
from dependencies.rbac import require_perm
from models.email_templates import EmailMngr
from schemas.email import (
    EmailBodyPatch,
    EmailTemplate,
    EmailTemplateDetail,
    EmailTemplatePatch,
    EmailTemplateUpload,
)

router = APIRouter()


@router.get(
    "",
    response_model=list[EmailTemplate],
    dependencies=[Depends(require_perm("email.read"))],
    summary="Email templates",
)
async def list_templates(
    mngr: EmailMngr = Depends(get_email_templates_mngr),
) -> list[EmailTemplate]:
    rows = await mngr.list_all()
    return [EmailTemplate.from_model(r) for r in rows]


@router.get(
    "/{tpl_id}",
    response_model=EmailTemplateDetail,
    dependencies=[Depends(require_perm("email.read"))],
    summary="Get email template",
)
async def get_template(
    tpl_id: int,
    mngr: EmailMngr = Depends(get_email_templates_mngr),
) -> EmailTemplateDetail:
    row = await mngr.by_id(tpl_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "template not found")
    body = await mngr.read_body(row)
    return EmailTemplateDetail.from_model_with_body(row, body)


@router.post(
    "",
    response_model=EmailTemplate,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_perm("email.create"))],
    summary="Create email template",
    description="Create an email template and store its body.",
)
async def create_template(
    body: EmailTemplateUpload,
    mngr: EmailMngr = Depends(get_email_templates_mngr),
) -> EmailTemplate:
    row = await mngr.create(body)
    await mngr.s.commit()
    return EmailTemplate.from_model(row)


@router.patch(
    "/{tpl_id}",
    response_model=EmailTemplate,
    dependencies=[Depends(require_perm("email.edit"))],
    summary="Update email template",
    description="Update template fields.",
)
async def patch_template(
    tpl_id: int,
    body: EmailTemplatePatch,
    mngr: EmailMngr = Depends(get_email_templates_mngr),
) -> EmailTemplate:
    row = await mngr.patch(tpl_id, body)
    await mngr.s.commit()
    return EmailTemplate.from_model(row)


@router.put(
    "/{tpl_id}/body",
    response_model=EmailTemplate,
    dependencies=[Depends(require_perm("email.edit"))],
    summary="Replace email body",
    description="Replace the template body.",
)
async def replace_body(
    tpl_id: int,
    body: EmailBodyPatch,
    mngr: EmailMngr = Depends(get_email_templates_mngr),
) -> EmailTemplate:
    row = await mngr.update_body(tpl_id, body.body)
    await mngr.s.commit()
    return EmailTemplate.from_model(row)


@router.delete(
    "/{tpl_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_perm("email.delete"))],
    summary="Delete email template",
)
async def delete_template(
    tpl_id: int, mngr: EmailMngr = Depends(get_email_templates_mngr)
) -> None:
    await mngr.delete(tpl_id)
    await mngr.s.commit()


__all__ = ["router"]
