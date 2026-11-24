"""DI для email-интеграции: шаблоны, триггеры, отправитель, диспетчер."""

from __future__ import annotations

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.db import get_db_session
from dependencies.mail import build_mail_svc
from dependencies.settings import SystemSettingsMngr, get_settings_mngr
from lifecycle.notifications import EmailSender
from models.email_templates import EmailMngr
from core.config import AppConfig


def get_email_templates_mngr(
    request: Request, session: AsyncSession = Depends(get_db_session)
) -> EmailMngr:
    cfg: AppConfig = request.app.state.settings
    return EmailMngr(session, cfg.EMAIL_TEMPLATES_DIR, sync_to_fs=cfg.email_sync_to_fs)


async def get_email_sender(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    settings: SystemSettingsMngr = Depends(get_settings_mngr),
) -> EmailSender:
    from lua.deps import get_lua_bus

    cfg: AppConfig = request.app.state.settings
    bus = get_lua_bus(request)
    mail = await build_mail_svc(settings, cfg, bus=bus, session=session)
    return EmailSender(mail, EmailMngr(session, cfg.EMAIL_TEMPLATES_DIR, sync_to_fs=cfg.email_sync_to_fs))


__all__ = [
    "get_email_templates_mngr",
    "get_email_sender",
]
