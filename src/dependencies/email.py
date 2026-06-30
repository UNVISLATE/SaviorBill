"""DI для email-интеграции: шаблоны, триггеры, отправитель, диспетчер."""

from __future__ import annotations

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.db import get_db_session
from dependencies.mail import build_mail_svc
from dependencies.settings import SystemSettingsMngr, get_settings_mngr
from integrations.email import EmailSender
from models.email_templates import EmailMngr
from utils.config import AppConfig


def get_email_templates_mngr(
    request: Request, session: AsyncSession = Depends(get_db_session)
) -> EmailMngr:
    cfg: AppConfig = request.app.state.settings
    return EmailMngr(session, cfg.EMAIL_TEMPLATES_DIR)


async def get_email_sender(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    settings: SystemSettingsMngr = Depends(get_settings_mngr),
) -> EmailSender:
    cfg: AppConfig = request.app.state.settings
    mail = await build_mail_svc(settings)
    return EmailSender(mail, EmailMngr(session, cfg.EMAIL_TEMPLATES_DIR))


__all__ = [
    "get_email_templates_mngr",
    "get_email_sender",
]
