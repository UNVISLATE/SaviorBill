"""Выдача услуги цифровым ключом из пула (``service_keys``)."""

from __future__ import annotations

from sqlalchemy import select

from lifecycle.delivery.base import BaseIssuer
from utils.datetime_utils import utc_now


class KeyService(BaseIssuer):
    """Берёт первый свободный ключ услуги и помечает его использованным."""

    async def issue(self, usvc, service, acc) -> None:  # noqa: ANN001 — ORM-объекты
        from models.service_keys import ServiceKeysModel

        key = await self.s.scalar(
            select(ServiceKeysModel)
            .where(
                ServiceKeysModel.service_id == service.id,
                ServiceKeysModel.is_used.is_(False),
            )
            .order_by(ServiceKeysModel.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if key is None:
            raise RuntimeError("нет доступных ключей для услуги")

        key.is_used = True
        key.order_id = usvc.id
        key.used_at = utc_now()
        usvc.digikey_id = key.id
        value = self.box.open(key.value) if self.box is not None else key.value
        usvc.public_data = {"key": value}
        usvc.private_data = {"digikey_id": key.id}

        if self.dispatcher is not None:
            from lifecycle.triggers.stock import check_and_fire_key_stock_triggers

            await check_and_fire_key_stock_triggers(self.s, service, self.dispatcher)

        # Если ключи для услуги закончились, мгновенно сбрасываем кэш каталога (out_of_stock: True)
        if self.bus is not None and getattr(self.bus, "vk", None) is not None:
            from sqlalchemy import func
            from services.catalog_cache import invalidate_catalog_cache

            rem_count = await self.s.scalar(
                select(func.count())
                .select_from(ServiceKeysModel)
                .where(
                    ServiceKeysModel.service_id == service.id,
                    ServiceKeysModel.is_used.is_(False),
                )
            )
            if rem_count == 0:
                await invalidate_catalog_cache(self.bus.vk)


__all__ = ["KeyService"]
