"""Проверка целостности шифрования (на каждом запуске)."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.system_settings import SystemSettingsModel
from utils.sec.box import SecBox

log = logging.getLogger("saviorbill.bootstrap")

Setting = SystemSettingsModel

_CANARY = "saviorbill-integrity-canary"


async def check_integrity(session: AsyncSession, box: SecBox) -> bool:
    """Проверить валидность ключа и читаемость сохранённых секретов."""
    # 1. Round-trip канарейки.
    try:
        if box.open(box.seal(_CANARY)) != _CANARY:
            log.critical("проверка ключа: round-trip не совпал")
            return False
    except Exception as exc:  # noqa: BLE001 - любой сбой ключа критичен
        log.critical("проверка ключа провалена: %s", exc)
        return False

    # 2. Расшифровка реально сохранённых секретов.
    rows = await session.scalars(
        select(SystemSettingsModel).where(SystemSettingsModel.is_secret.is_(True))
    )
    bad: list[str] = []
    for row in rows:
        if row.value is None:
            continue
        try:
            box.open(row.value)
        except Exception:  # noqa: BLE001 - повреждённый/чужой секрет
            bad.append(row.key)

    if bad:
        log.critical(
            "не расшифровываются секреты (ключ заменён/повреждён): %s",
            ", ".join(bad),
        )
        return False

    log.info("проверка целостности шифрования: OK")
    return True


__all__ = ["check_integrity"]
