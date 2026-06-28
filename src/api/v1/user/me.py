"""Профиль текущего пользователя (/api/v1/user/me)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from dependencies.auth import get_current_acc
from models.user import Account
from schemas.auth import AccOut

router = APIRouter()


@router.get("/me", response_model=AccOut, summary="Профиль текущего пользователя")
async def me(acc: Account = Depends(get_current_acc)) -> AccOut:
    """Вернуть данные текущего аккаунта по access-токену."""
    return AccOut.from_account(acc)


__all__ = ["router"]
