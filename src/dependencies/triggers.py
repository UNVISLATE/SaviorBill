"""DI для триггеров: менеджер и диспетчер действий."""

from __future__ import annotations

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.db import get_db_session
from lua.deps import get_lua_bus_configured
from dependencies.mail import build_mail_svc
from dependencies.settings import SystemSettingsMngr, get_settings_mngr
from notifications.email import EmailSender
from automation.triggers import EmailAction, LuaAction, TriggerDispatcher
from models.email_templates import EmailMngr
from models.triggers import TriggerMngr
from core.config import AppConfig
from lua.bus import LuaBus


def get_trigger_mngr(
    session: AsyncSession = Depends(get_db_session),
) -> TriggerMngr:
    """Менеджер триггеров.

    :arg session: сессия БД.
    :return: ``TriggerMngr``.
    """
    return TriggerMngr(session)


async def get_dispatcher(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    settings: SystemSettingsMngr = Depends(get_settings_mngr),
    bus: LuaBus = Depends(get_lua_bus_configured),
) -> TriggerDispatcher:
    """Собрать диспетчер триггеров со всеми действиями.

    :arg request: запрос (ресурсы приложения).
    :arg session: сессия БД.
    :arg settings: менеджер настроек (для SMTP).
    :arg bus: шина LuaWorker.
    :return: ``TriggerDispatcher``.
    """
    cfg: AppConfig = request.app.state.settings
    templates = EmailMngr(session, cfg.EMAIL_TEMPLATES_DIR)
    mail = await build_mail_svc(settings)
    actions = {
        EmailAction.key: EmailAction(EmailSender(mail, templates), templates),
        LuaAction.key: LuaAction(bus, session),
    }
    return TriggerDispatcher(TriggerMngr(session), actions, settings)


__all__ = ["get_trigger_mngr", "get_dispatcher"]
