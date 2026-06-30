"""Профиль текущего администратора (/api/v1/admin/me)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from dependencies.auth import get_current_acc
from models.user import UserModel
from schemas.auth import AdminMe

router = APIRouter()


@router.get(
    "/me",
    response_model=AdminMe,
    summary="Профиль администратора",
    description=(
        "Текущий аккаунт вместе с деревом прав его роли — для отрисовки "
        "админ-панели (какие разделы доступны)."
    ),
)
async def admin_me(acc: UserModel = Depends(get_current_acc)) -> AdminMe:
    """Вернуть профиль текущего администратора и его права."""
    return AdminMe.from_account(acc)


__all__ = ["router"]
