"""DI-гейт прав доступа поверх RBAC."""

from __future__ import annotations

from typing import Callable

from fastapi import Depends, HTTPException, status

from dependencies.auth import get_current_acc
from models.user import Account
from utils.rbac import has_perm, reg_perm


def require_perm(path: str) -> Callable:
    """Зависимость-гейт: пускает только аккаунт с правом ``path``.

    Побочно регистрирует право в реестре (для ``GET /admin/perms``).
    Использование::

        @router.get("/users", dependencies=[Depends(require_perm("users.read"))])
    """
    reg_perm(path)

    async def _dep(acc: Account = Depends(get_current_acc)) -> Account:
        perms = acc.role.perms if acc.role else None
        if not has_perm(perms, path):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, detail=f"недостаточно прав: {path}"
            )
        return acc

    return _dep


__all__ = ["require_perm"]
