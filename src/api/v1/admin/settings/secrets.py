"""Админ: ротация ключа шифрования секретов (/api/v1/admin/settings/secrets).

Перевод существующих зашифрованных строк на самый новый ключ ``SECRETS_KEY``
после его ротации (см. ``security/sec/rotate.py`` — сам механизм ре-шифровки
существовал раньше, но без вызывающей стороны; это его единственная точка
входа). Owner-only: массовая расшифровка/перешифровка всех секретных строк —
чувствительная операция, которую не должен запускать никто, кроме владельца
инсталляции.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.db import get_db_session
from dependencies.rbac import require_perm
from dependencies.sec import get_secbox
from security.sec.box import SecBox
from security.sec.rotate import reencrypt_all

router = APIRouter()


@router.post(
    "/reencrypt",
    summary="Reencrypt all secret columns",
    description=(
        "Rewrite service_keys/settings/payment_providers/oauth_providers "
        "secret columns with the newest SECRETS_KEY. Run after adding a new "
        "key to SECRETS_KEY, before removing the old one from the list."
    ),
)
async def reencrypt_secrets(
    session: AsyncSession = Depends(get_db_session),
    box: SecBox = Depends(get_secbox),
    _acc=Depends(require_perm("settings.secrets.reencrypt")),
) -> dict[str, int]:
    return await reencrypt_all(session, box)


__all__ = ["router"]
