"""FastAPI-зависимости для гостевого чекаута и клейма аккаунтов."""

from __future__ import annotations

import valkey.asyncio as valkey
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.db import get_db_session
from dependencies.email import get_email_sender
from dependencies.settings import SystemSettingsMngr, get_settings_mngr
from dependencies.valkey import get_valkey_client
from lifecycle.notifications import EmailSender
from services.guest_checkout import GuestCheckoutSvc


def get_guest_checkout_svc(
    session: AsyncSession = Depends(get_db_session),
    vk: valkey.Valkey = Depends(get_valkey_client),
    sender: EmailSender = Depends(get_email_sender),
    settings: SystemSettingsMngr = Depends(get_settings_mngr),
) -> GuestCheckoutSvc:
    """Инстанцировать сервис гостевого чекаута."""
    return GuestCheckoutSvc(
        session=session,
        vk=vk,
        sender=sender,
        settings=settings,
    )


__all__ = ["GuestCheckoutSvc", "get_guest_checkout_svc"]
