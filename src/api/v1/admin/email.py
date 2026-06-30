"""Админ: управление email-шаблонами (/api/v1/admin/email)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from dependencies.email import get_email_templates_mngr
from dependencies.rbac import require_perm
from models.email_templates import EmailMngr
from schemas.email import (
    EmailBodyPatch,
    EmailTemplate,
    EmailTemplatePatch,
    EmailTemplateUpload,
)

router = APIRouter()


@router.get(
    "/email/templates",
    response_model=list[EmailTemplate],
    dependencies=[Depends(require_perm("email.read"))],
    summary="Список email-шаблонов",
)
async def list_templates(
    mngr: EmailMngr = Depends(get_email_templates_mngr),
) -> list[EmailTemplate]:
    rows = await mngr.list_all()
    return [EmailTemplate.from_model(r) for r in rows]


@router.post(
    "/email/templates",
    response_model=EmailTemplate,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_perm("email.edit"))],
    summary="Создать email-шаблон",
    description=(
        "Сохраняет тело письма (jinja2) в монтируемую папку под сгенерированным "
        "именем и регистрирует шаблон в БД."
    ),
)
async def create_template(
    body: EmailTemplateUpload,
    mngr: EmailMngr = Depends(get_email_templates_mngr),
) -> EmailTemplate:
    row = await mngr.create(body)
    await mngr.s.commit()
    return EmailTemplate.from_model(row)


@router.patch(
    "/email/templates/{tpl_id}",
    response_model=EmailTemplate,
    dependencies=[Depends(require_perm("email.edit"))],
    summary="Изменить поля email-шаблона",
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
    "/email/templates/{tpl_id}/body",
    response_model=EmailTemplate,
    dependencies=[Depends(require_perm("email.edit"))],
    summary="Заменить тело email-шаблона",
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
    "/email/templates/{tpl_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_perm("email.edit"))],
    summary="Удалить email-шаблон",
)
async def delete_template(
    tpl_id: int, mngr: EmailMngr = Depends(get_email_templates_mngr)
) -> None:
    await mngr.delete(tpl_id)
    await mngr.s.commit()


__all__ = ["router"]
