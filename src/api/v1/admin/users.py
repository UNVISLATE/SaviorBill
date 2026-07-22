"""Админ: пользователи, их услуги, платежи и OAuth-привязки."""

from __future__ import annotations

import valkey.asyncio as valkey
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.db import get_db_session
from dependencies.media import get_media_mngr
from dependencies.rbac import require_perm
from dependencies.valkey import get_valkey_client
from models.roles import Role
from models.system_media import SystemMediaMngr
from models.user import UserModel
from models.user_oauth import UserOauthModel, UserOauthMngr
from models.user_payments import UserPaymentsModel
from models.user_services import UserServicesModel
from schemas.auth import Account, AvatarSet
from schemas.orders import OrderAdmin
from schemas.page import Page
from schemas.payments import PaymentAdmin
from schemas.user import OAuthConnAdmin, User, UserDetail, UserPatch
from services.account import account_response, release_old_avatar
from utils.pagination import (
    PageParams,
    apply_sort,
    page_params,
    paginate,
    paginate_search,
    q_param,
    sort_param,
)

router = APIRouter()

_SORT_FIELDS = {"id", "login", "email", "created_at", "last_login", "role_id", "balance"}


async def _get_user(session: AsyncSession, user_id: int) -> UserModel:
    """Загрузить аккаунт или вернуть 404.

    :arg session: сессия БД; :arg user_id: id аккаунта.
    :return: модель аккаунта.
    """
    acc = await session.get(UserModel, user_id)
    if acc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")
    return acc


@router.get(
    "",
    response_model=Page[User],
    dependencies=[Depends(require_perm("users.read"))],
    summary="Users",
    description="Paginated user list. `q` searches login/email (falls back to "
    "fuzzy matching if nothing is found); `sort` accepts "
    f"{'/'.join(sorted(_SORT_FIELDS))} (prefix with '-' for descending).",
)
async def list_users(
    pp: PageParams = Depends(page_params),
    q: str | None = Depends(q_param),
    sort: str | None = Depends(sort_param),
    session: AsyncSession = Depends(get_db_session),
) -> Page[User]:
    """Постраничный список аккаунтов."""
    stmt = apply_sort(select(UserModel), UserModel, sort, _SORT_FIELDS)
    if sort is None:
        stmt = stmt.order_by(UserModel.id)
    items, total, has_more = await paginate_search(
        session,
        stmt,
        UserModel,
        User.from_model,
        limit=pp.limit,
        offset=pp.offset,
        q=q,
        search_fields=("login", "email"),
        fuzzy_fields=("login", "email"),
    )
    return Page(
        items=items, total=total, limit=pp.limit, offset=pp.offset, has_more=has_more
    )


@router.get(
    "/{user_id}",
    response_model=UserDetail,
    dependencies=[Depends(require_perm("users.read"))],
    summary="User details",
    description="Profile, role, OAuth links, and usage counters.",
)
async def user_detail(
    user_id: int, session: AsyncSession = Depends(get_db_session)
) -> UserDetail:
    """Полная карточка пользователя со связанными агрегатами."""
    acc = await _get_user(session, user_id)
    conns = await UserOauthMngr(session).list_for_account(user_id)
    services_count = await session.scalar(
        select(func.count())
        .select_from(UserServicesModel)
        .where(UserServicesModel.account_id == user_id)
    )
    payments_count = await session.scalar(
        select(func.count())
        .select_from(UserPaymentsModel)
        .where(UserPaymentsModel.account_id == user_id)
    )
    return UserDetail.from_model(
        acc, conns, int(services_count or 0), int(payments_count or 0)
    )


@router.get(
    "/{user_id}/profile",
    response_model=Account,
    dependencies=[Depends(require_perm("users.read"))],
    summary="User profile (admin view)",
    description=(
        "Тот же формат, что и `GET /v1/user/me`, но для произвольного "
        "аккаунта — источник данных вкладки 'Профиль' в админском Drawer при "
        "просмотре чужого профиля (см. IMPLEMENTATION_PLAN.md §4)."
    ),
)
async def user_profile_admin(
    user_id: int, session: AsyncSession = Depends(get_db_session)
) -> Account:
    acc = await _get_user(session, user_id)
    return await account_response(acc, session)


@router.patch(
    "/{user_id}",
    response_model=User,
    dependencies=[Depends(require_perm("users.edit"))],
    summary="Update user",
    description="Update the provided user fields.",
)
async def edit_user(
    user_id: int,
    body: UserPatch,
    session: AsyncSession = Depends(get_db_session),
) -> User:
    """Частично обновить аккаунт.

    :arg user_id: id аккаунта; :arg body: изменяемые поля (все опциональны).
    :return: обновлённый аккаунт.
    """
    acc = await _get_user(session, user_id)
    data = body.model_dump(exclude_unset=True)
    if "role_id" in data and data["role_id"] != acc.role_id:
        if acc.role and acc.role.key == "owner":
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "the owner role cannot be changed"
            )
        new_role = await session.get(Role, data["role_id"]) if data["role_id"] else None
        if new_role is not None and new_role.key == "owner":
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "the owner role cannot be assigned"
            )
    for field, value in data.items():
        setattr(acc, field, value)
    await session.commit()
    return User.from_model(acc)


@router.get(
    "/{user_id}/services",
    response_model=Page[OrderAdmin],
    dependencies=[Depends(require_perm("orders.read"))],
    summary="User services",
    description="User orders with private data.",
)
async def user_services(
    user_id: int,
    pp: PageParams = Depends(page_params),
    session: AsyncSession = Depends(get_db_session),
) -> Page[OrderAdmin]:
    """Список услуг (заказов) пользователя (постранично)."""
    await _get_user(session, user_id)
    stmt = (
        select(UserServicesModel)
        .where(UserServicesModel.account_id == user_id)
        .order_by(UserServicesModel.id.desc())
    )
    items, total, has_more = await paginate(
        session, stmt, OrderAdmin.from_model, limit=pp.limit, offset=pp.offset
    )
    return Page(
        items=items, total=total, limit=pp.limit, offset=pp.offset, has_more=has_more
    )


@router.get(
    "/{user_id}/payments",
    response_model=Page[PaymentAdmin],
    dependencies=[Depends(require_perm("purchases.read"))],
    summary="User payments",
    description="User payments with private data.",
)
async def user_payments(
    user_id: int,
    pp: PageParams = Depends(page_params),
    session: AsyncSession = Depends(get_db_session),
) -> Page[PaymentAdmin]:
    """Список платежей пользователя (постранично)."""
    await _get_user(session, user_id)
    stmt = (
        select(UserPaymentsModel)
        .where(UserPaymentsModel.account_id == user_id)
        .order_by(UserPaymentsModel.id.desc())
    )
    items, total, has_more = await paginate(
        session, stmt, PaymentAdmin.from_model, limit=pp.limit, offset=pp.offset
    )
    return Page(
        items=items, total=total, limit=pp.limit, offset=pp.offset, has_more=has_more
    )


@router.get(
    "/{user_id}/oauth",
    response_model=list[OAuthConnAdmin],
    dependencies=[Depends(require_perm("users.read"))],
    summary="User OAuth links",
    description="OAuth accounts linked to the user.",
)
async def user_oauth(
    user_id: int, session: AsyncSession = Depends(get_db_session)
) -> list[OAuthConnAdmin]:
    """Список OAuth-привязок пользователя."""
    await _get_user(session, user_id)
    rows = await session.scalars(
        select(UserOauthModel)
        .where(UserOauthModel.account_id == user_id)
        .order_by(UserOauthModel.id)
    )
    return [OAuthConnAdmin.from_model(r) for r in rows]


@router.put(
    "/{user_id}/avatar",
    response_model=Account,
    dependencies=[Depends(require_perm("admin.media.manage_any"))],
    summary="Force-set user avatar (admin)",
    description=(
        "Set a user's avatar to any media (not just the user's own) — "
        "separate from the self-service `/user/me/avatar`, which only "
        "allows setting your own media. `media_id: null` removes the avatar."
    ),
)
async def set_user_avatar(
    request: Request,
    user_id: int,
    body: AvatarSet,
    session: AsyncSession = Depends(get_db_session),
    media: SystemMediaMngr = Depends(get_media_mngr),
    vk: valkey.Valkey = Depends(get_valkey_client),
) -> Account:
    acc = await _get_user(session, user_id)
    if body.media_id is not None:
        m = await media.by_id(body.media_id)
        if m is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "media not found")

    old_media_id = acc.avatar_media_id
    acc.avatar_media_id = body.media_id
    await session.commit()
    await session.refresh(acc)

    if old_media_id is not None and old_media_id != body.media_id:
        old = await media.by_id(old_media_id)
        if old is not None:
            await release_old_avatar(
                request, vk, media, old, exclude_account_id=acc.id
            )
        await session.commit()

    return await account_response(acc, session)


__all__ = ["router"]
