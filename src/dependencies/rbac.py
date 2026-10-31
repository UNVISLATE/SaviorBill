from __future__ import annotations

from typing import Callable

from fastapi import Depends, HTTPException, Request, status

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

    async def _dep(
        request: Request,
        acc: UserModel = Depends(get_current_acc),
    ) -> UserModel:
        # Для App Token права проверяются строго по его собственному списку permissions
        app_token = getattr(request.state, "app_token", None)
        if app_token is not None:
            if not has_perm(app_token.perms_tree, path):
                raise HTTPException(
                    status.HTTP_403_FORBIDDEN, detail=f"insufficient permissions: {path}"
                )
            return acc

        # owner может ВСЁ, независимо от содержимого perms — единственная
        # неприкасаемая роль (см. IMPLEMENTATION_PLAN.md, "Решения по
        # открытым вопросам" п.1).
        if acc.role and acc.role.key == "owner":
            return acc
        perms = acc.role.perms if acc.role else None
        if not has_perm(perms, path):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, detail=f"insufficient permissions: {path}"
            )
        return acc

    # Метка для авто-документации требуемого права в OpenAPI (см. utils/openapi.py).
    _dep._required_perm = path
    return _dep


def require_any_perm(*paths: str) -> Callable:
    """Зависимость-гейт: пускает аккаунт, если у него есть хотя бы одно право из ``paths``.

    Побочно регистрирует все переданные права в реестре.
    """
    for path in paths:
        reg_perm(path)

    async def _dep(
        request: Request,
        acc: UserModel = Depends(get_current_acc),
    ) -> UserModel:
        app_token = getattr(request.state, "app_token", None)
        if app_token is not None:
            if not any(has_perm(app_token.perms_tree, p) for p in paths):
                raise HTTPException(
                    status.HTTP_403_FORBIDDEN,
                    detail=f"insufficient permissions: any of {list(paths)}",
                )
            return acc

        if acc.role and acc.role.key == "owner":
            return acc
        perms = acc.role.perms if acc.role else None
        if not any(has_perm(perms, p) for p in paths):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail=f"insufficient permissions: any of {list(paths)}",
            )
        return acc

    _dep._required_perms = list(paths)
    return _dep


__all__ = ["require_perm", "require_any_perm"]
