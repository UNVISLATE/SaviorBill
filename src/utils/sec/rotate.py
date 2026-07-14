"""Фоновая ре-шифровка строк после ротации ключа ``SecBox`` (IMPLEMENTATION_PLAN §12).

Ротация ключа сама по себе (см. ``utils/sec/box.py``) не требует немедленного
bulk-rewrite: ``MultiFernet`` умеет расшифровывать данные и старым, и новым
ключом сразу после того, как новый ключ добавлен первым в список
``SECRETS_KEY``. Эта джоба — опциональный, safe-to-interrupt механизм для
постепенного перевода существующих строк на новый ключ (после чего старый
ключ можно безопасно убрать из списка).

Каждая строка обрабатывается в отдельной транзакции (``open()`` → ``seal()``
→ ``commit``), поэтому падение процесса в середине прохода оставляет часть
строк уже в новом формате, часть — в старом, и это нормально: обе версии
читаемы, пока старый ключ ещё в списке ``SECRETS_KEY``. Джобу можно запускать
повторно в любой момент — она идемпотентна (повторная ре-шифровка уже
переведённой строки просто перезаписывает её тем же новым ключом).
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.oauth_providers import OAuthProvidersModel
from models.payment_providers import PaymentProvidersModel
from models.service_keys import ServiceKeysModel
from models.system_settings import SystemSettingsModel
from utils.sec.box import SecBox

log = logging.getLogger("saviorbill.sec.rotate")


async def _reencrypt_rows(
    session: AsyncSession,
    box: SecBox,
    *,
    model: type,
    column: str,
    where_secret: bool = False,
) -> int:
    """Пройти по строкам модели, перешифровав непустое поле ``column``.

    :arg where_secret: если ``True`` — обрабатывать только строки с
        ``is_secret=True`` (таблица ``settings``, где часть строк не
        зашифрована вовсе).
    :return: число фактически перешифрованных строк.
    """
    stmt = select(model)
    if where_secret:
        stmt = stmt.where(model.is_secret.is_(True))
    ids = [
        row.id if hasattr(row, "id") else getattr(row, "key")
        for row in await session.scalars(stmt)
    ]

    done = 0
    for pk in ids:
        # Отдельная транзакция на строку — падение на середине не портит остальные.
        row = await session.get(model, pk)
        if row is None:
            continue
        value = getattr(row, column)
        if not value:
            continue
        try:
            plain = box.open(value)
        except RuntimeError:
            log.warning(
                "rotate: failed to decrypt %s.%s (pk=%r) — skip",
                model.__tablename__,
                column,
                pk,
            )
            continue
        setattr(row, column, box.seal(plain))
        await session.commit()
        done += 1
    return done


async def reencrypt_all(session: AsyncSession, box: SecBox) -> dict[str, int]:
    """Перешифровать все известные зашифрованные колонки самым новым ключом.

    Таблицы: ``service_keys.value`` (цифровые ключи), ``settings.value``
    (только строки ``is_secret=True``), ``payment_providers.secrets_enc``,
    ``oauth_providers.secrets_enc``.

    :return: число перешифрованных строк по каждой таблице (для отчёта/лога).
    """
    counts = {
        "service_keys": await _reencrypt_rows(
            session, box, model=ServiceKeysModel, column="value"
        ),
        "settings": await _reencrypt_rows(
            session, box, model=SystemSettingsModel, column="value", where_secret=True
        ),
        "payment_providers": await _reencrypt_rows(
            session, box, model=PaymentProvidersModel, column="secrets_enc"
        ),
        "oauth_providers": await _reencrypt_rows(
            session, box, model=OAuthProvidersModel, column="secrets_enc"
        ),
    }
    log.info("rotate: lines reencrypted: %r", counts)
    return counts


__all__ = ["reencrypt_all"]
