"""Профиль текущего администратора (/api/v1/admin/me)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from dependencies.auth import get_current_acc
from models.user import UserModel
from schemas.auth import AdminMe

router = APIRouter()


@router.get(
    "/me",
    response_model=AdminMe,
    summary="Admin profile",
    description="Current account with role permissions. Roles without "
    "admin_login_allowed (other than 'owner') are denied admin access "
    "entirely — this is the actual gate into the admin panel, not just a "
    "UI nicety.",
)
async def admin_me(acc: UserModel = Depends(get_current_acc)) -> AdminMe:
    """Вернуть профиль текущего администратора и его права."""
    is_owner = acc.role is not None and acc.role.key == "owner"
    if not is_owner and not (acc.role and acc.role.admin_login_allowed):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "your role is not allowed to log into the admin panel",
        )
    return AdminMe.from_account(acc)


__all__ = ["router"]
