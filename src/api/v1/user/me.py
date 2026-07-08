"""Профиль текущего пользователя (/api/v1/user/me)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from dependencies.auth import get_current_acc
from dependencies.rbac import require_perm
from models.user import UserModel
from schemas.auth import Account

router = APIRouter()


@router.get(
    "/me",
    response_model=Account,
    summary="Профиль текущего пользователя",
    dependencies=[Depends(require_perm("user.profile.read"))],
)
async def me(acc: UserModel = Depends(get_current_acc)) -> Account:
    """Вернуть данные текущего аккаунта по access-токену."""
    return Account.from_account(acc)


__all__ = ["router"]
