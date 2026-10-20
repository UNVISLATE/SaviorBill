"""Проверка остатка цифровых ключей услуги и вызов триггеров."""

from __future__ import annotations

import logging
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from lifecycle.triggers.events import TriggerEvent

log = logging.getLogger("saviorbill.triggers.stock")


async def check_and_fire_key_stock_triggers(
    session: AsyncSession,
    service,  # noqa: ANN001 — ServiceModel
    dispatcher,  # noqa: ANN001 — TriggerDispatcher | None
) -> None:
    """Проверить доступный остаток цифровых ключей услуги и при необходимости вызвать триггер.

    Вызывает:
      - ``TriggerEvent.SERVICE_KEYS_EMPTY`` — если доступных ключей 0 шт.
      - ``TriggerEvent.SERVICE_KEYS_LOW`` — если доступных ключей меньше установленного порога.
    """
    if dispatcher is None or service is None:
        return

    from models.service_keys import ServiceKeysModel
    from models.system_settings import SystemSettingsMngr

    try:
        settings_mngr = SystemSettingsMngr(session)
        threshold = await settings_mngr.get_int("service.keys_low_threshold", 5) or 5

        remaining = await session.scalar(
            select(func.count(ServiceKeysModel.id)).where(
                ServiceKeysModel.service_id == service.id,
                ServiceKeysModel.is_used.is_(False),
            )
        )
        remaining = int(remaining or 0)

        ctx = {
            "service_id": service.id,
            "service_name": service.name,
            "service_slug": service.slug,
            "keys_left": remaining,
            "threshold": threshold,
        }

        if remaining == 0:
            await dispatcher.fire(TriggerEvent.SERVICE_KEYS_EMPTY, ctx)
        elif remaining < threshold:
            await dispatcher.fire(TriggerEvent.SERVICE_KEYS_LOW, ctx)
    except Exception:  # noqa: BLE001
        log.exception(
            "ошибка при проверке остатка ключей для услуги id=%s", getattr(service, "id", None)
        )


__all__ = ["check_and_fire_key_stock_triggers"]
