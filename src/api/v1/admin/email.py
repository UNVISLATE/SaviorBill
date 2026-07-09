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
from utils.apidoc import with_fields

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


@router.get(
    "/email/templates/{tpl_id}",
    response_model=EmailTemplateDetail,
    dependencies=[Depends(require_perm("email.read"))],
    summary="Получить один email-шаблон (с телом)",
)
async def get_template(
    tpl_id: int,
    mngr: EmailMngr = Depends(get_email_templates_mngr),
) -> EmailTemplateDetail:
    row = await mngr.by_id(tpl_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "шаблон не найден")
    body = await mngr.read_body(row)
    return EmailTemplateDetail.from_model_with_body(row, body)


@router.post(
    "/email/templates",
    response_model=EmailTemplate,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_perm("email.create"))],
    summary="Создать email-шаблон",
    description=with_fields(
        (
            "Сохраняет тело письма (jinja2) в монтируемую папку под сгенерированным "
            "именем и регистрирует шаблон в БД."
        ),
        EmailTemplateUpload,
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
    description=with_fields(
        "Частично обновляет email-шаблон — передаются только изменяемые поля.",
        EmailTemplatePatch,
    ),
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
    description=with_fields(
        "Заменяет тело (jinja2) существующего email-шаблона.",
        EmailBodyPatch,
    ),
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
    dependencies=[Depends(require_perm("email.delete"))],
    summary="Удалить email-шаблон",
)
async def delete_template(
    tpl_id: int, mngr: EmailMngr = Depends(get_email_templates_mngr)
) -> None:
    await mngr.delete(tpl_id)
    await mngr.s.commit()


__all__ = ["router"]
