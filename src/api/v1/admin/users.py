"""Админ: пользователи и их товары."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.db import get_db_session
from dependencies.rbac import require_perm
from models.user import UserModel
from models.user_services import UserServicesModel
from schemas.user import User, UserPatch
from schemas.orders import OrderAdmin

router = APIRouter()


@router.get(
    "/users",
    response_model=list[User],
    dependencies=[Depends(require_perm("users.read"))],
    summary="Список пользователей",
)
async def list_users(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db_session),
) -> list[User]:
    rows = await session.scalars(
        select(UserModel).order_by(UserModel.id).limit(limit).offset(offset)
    )
    return [User.from_model(r) for r in rows]


@router.patch(
    "/users/{user_id}",
    response_model=User,
    dependencies=[Depends(require_perm("users.edit"))],
    summary="Редактировать пользователя",
    description="Меняет только переданные поля (email, активность, роль, балансы).",
)
async def edit_user(
    user_id: int,
    body: UserPatch,
    session: AsyncSession = Depends(get_db_session),
) -> User:
    acc = await session.get(UserModel, user_id)
    if acc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "пользователь не найден")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(acc, field, value)
    await session.commit()
    return User.from_model(acc)


@router.get(
    "/users/{user_id}/orders",
    response_model=list[OrderAdmin],
    dependencies=[Depends(require_perm("orders.read"))],
    summary="Товары пользователя",
    description="Заказы пользователя с приватными данными (для поддержки).",
)
async def user_orders(
    user_id: int, session: AsyncSession = Depends(get_db_session)
) -> list[OrderAdmin]:
    rows = await session.scalars(
        select(UserServicesModel)
        .where(UserServicesModel.account_id == user_id)
        .order_by(UserServicesModel.id.desc())
    )
    return [OrderAdmin.from_model(r) for r in rows]


__all__ = ["router"]
