"""Внутренний API отправки писем для LuaWorker."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from dependencies.email import get_email_sender, get_email_templates_mngr
from lifecycle.notifications import EmailSender
from models.email_templates import EmailMngr
from schemas.types import NormEmail

from .service_keys import require_lua_token

log = logging.getLogger("saviorbill.internal.email")

router = APIRouter(prefix="/email")


class LuaSendEmailIn(BaseModel):
    to: NormEmail = Field(description="Recipient email address")
    template: str | int = Field(description="Email template slug (str) or ID (int)")
    context: dict[str, Any] = Field(default_factory=dict, description="Template rendering context")
    from_email: str | None = Field(default=None, description="Optional sender email address override")
    from_name: str | None = Field(default=None, description="Optional sender display name override")


@router.post(
    "/send",
    dependencies=[Depends(require_lua_token)],
    summary="Internal send email from LuaWorker",
    description="Render a Jinja2 template with context and send via configured mail transport.",
)
async def send_email_internal(
    body: LuaSendEmailIn,
    sender: EmailSender = Depends(get_email_sender),
    mngr: EmailMngr = Depends(get_email_templates_mngr),
) -> dict:
    if isinstance(body.template, int) or (isinstance(body.template, str) and body.template.isdigit()):
        tpl = await mngr.by_id(int(body.template))
    else:
        tpl = await mngr.by_slug(str(body.template))

    if tpl is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"Email template '{body.template}' not found",
        )
    if not tpl.is_active:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Email template '{body.template}' is inactive",
        )

    try:
        await sender.send_by_template(
            tpl,
            body.to,
            body.context,
            from_email=body.from_email,
            from_name=body.from_name,
        )
    except Exception as exc:
        log.exception("Internal email send failed: %s", exc)
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            f"Failed to send email: {exc}",
        )

    return {"ok": True}


__all__ = ["router"]
