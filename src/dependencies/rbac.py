"""DI-гейт прав доступа поверх RBAC."""

from __future__ import annotations

from typing import Callable

from fastapi import Depends, HTTPException, status

from dependencies.auth import get_current_acc
from models.user import UserModel
from security.rbac import has_perm, reg_perm


def require_perm(path: str) -> Callable:
    """Зависимость-гейт: пускает только аккаунт с правом ``path``.

    Побочно регистрирует право в реестре (для ``GET /admin/perms``).
    Использование::
        @router.get("/users", dependencies=[Depends(require_perm("users.read"))])
    """
    reg_perm(path)

    async def _dep(acc: UserModel = Depends(get_current_acc)) -> UserModel:
        perms = acc.role.perms if acc.role else None
        if not has_perm(perms, path):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, detail=f"insufficient permissions: {path}"
            )
        return acc

    # Метка для авто-документации требуемого права в OpenAPI (см. utils/openapi.py).
    _dep._required_perm = path
    return _dep


__all__ = ["require_perm"]
