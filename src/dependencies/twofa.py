"""Гейт второго фактора для админских роутов.

Настройка ``auth.2fa.required_for_admin`` делает 2FA обязательной для ролей,
допущенных в админку: пока фактор не включён, аккаунт не может выполнить ни
одного админского действия. Исключение — ``GET /admin/me`` и сами роуты
включения 2FA, иначе интерфейсу было бы нечем показать экран настройки.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status

from dependencies.auth import get_current_acc
from dependencies.settings import SystemSettingsMngr, get_settings_mngr
from models.user import UserModel

#: Код в ответе, по которому UI понимает, что нужно показать настройку 2FA.
TOTP_SETUP_REQUIRED = "totp_setup_required"

_EXEMPT_SUFFIXES = ("/admin/me",)


async def require_2fa(
    request: Request,
    acc: UserModel = Depends(get_current_acc),
    settings: SystemSettingsMngr = Depends(get_settings_mngr),
) -> UserModel:
    """Не пускать админа без включённой 2FA, если она обязательна."""
    if acc.totp_enabled:
        return acc
    if request.url.path.endswith(_EXEMPT_SUFFIXES):
        return acc
    if not (acc.role and acc.role.admin_login_allowed):
        return acc
    required = await settings.get_bool("auth.2fa.required_for_admin", False)
    if not required:
        return acc
    raise HTTPException(
        status.HTTP_403_FORBIDDEN,
        detail=TOTP_SETUP_REQUIRED,
    )


__all__ = ["TOTP_SETUP_REQUIRED", "require_2fa"]
