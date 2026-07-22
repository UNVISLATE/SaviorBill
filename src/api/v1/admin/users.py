"""Админ: пользователи, их услуги, платежи и OAuth-привязки."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import valkey.asyncio as valkey
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.db import get_db_session
from dependencies.media import get_media_mngr
from dependencies.rbac import require_perm
from security.rbac import has_perm, reg_perm
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
from schemas.user import (
    BalanceAdjust,
    OAuthConnAdmin,
    User,
    UserDetail,
    UserPatch,
    UserStats,
)
from services.account import account_response, release_old_avatar
from services.audit import audit
from utils.datetime_utils import utc_now
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

reg_perm("users.admin.role.edit")  # проверяется вручную внутри edit_user
reg_perm("users.admin.balance.edit")  # проверяется вручную в edit_user и /balance

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
    "/stats",
    response_model=UserStats,
    dependencies=[Depends(require_perm("users.read"))],
    summary="User registration stats",
    description="Total users + registrations bucketed by common periods; "
    "pass both `from_`/`to` for an additional custom-range count.",
)
async def user_stats(
    from_: datetime | None = None,
    to: datetime | None = None,
    session: AsyncSession = Depends(get_db_session),
) -> UserStats:
    async def _count(since: datetime | None) -> int:
        stmt = select(func.count()).select_from(UserModel)
        if since is not None:
            stmt = stmt.where(UserModel.created_at >= since)
        return int(await session.scalar(stmt) or 0)

    now = utc_now()
    custom = None
    if from_ is not None and to is not None:
        custom = int(
            await session.scalar(
                select(func.count())
                .select_from(UserModel)
                .where(UserModel.created_at >= from_, UserModel.created_at <= to)
            )
            or 0
        )
    return UserStats(
        total=await _count(None),
        registered_all_time=await _count(None),
        registered_1d=await _count(now - timedelta(days=1)),
        registered_7d=await _count(now - timedelta(days=7)),
        registered_30d=await _count(now - timedelta(days=30)),
        registered_90d=await _count(now - timedelta(days=90)),
        registered_custom=custom,
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
    summary="Update user",
    description="Update the provided user fields. Changing `role_id` "
    "additionally requires `users.admin.role.edit`.",
)
async def edit_user(
    user_id: int,
    body: UserPatch,
    session: AsyncSession = Depends(get_db_session),
    caller: UserModel = Depends(require_perm("users.admin.edit")),
) -> User:
    """Частично обновить аккаунт.

    :arg user_id: id аккаунта; :arg body: изменяемые поля (все опциональны).
    :return: обновлённый аккаунт.
    """
    acc = await _get_user(session, user_id)
    data = body.model_dump(exclude_unset=True)
    if "role_id" in data and data["role_id"] != acc.role_id:
        caller_perms = caller.role.perms if caller.role else None
        if not (caller.role and caller.role.key == "owner") and not has_perm(
            caller_perms, "users.admin.role.edit"
        ):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "insufficient permissions: users.admin.role.edit",
            )
        if acc.role and acc.role.key == "owner":
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "the owner role cannot be changed"
            )
        new_role = await session.get(Role, data["role_id"]) if data["role_id"] else None
        if new_role is not None and new_role.key == "owner":
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "the owner role cannot be assigned"
            )
    if ("balance" in data or "bonus_balance" in data) and not (
        caller.role and caller.role.key == "owner"
    ):
        caller_perms = caller.role.perms if caller.role else None
        if not has_perm(caller_perms, "users.admin.balance.edit"):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "insufficient permissions: users.admin.balance.edit",
            )
    for field, value in data.items():
        setattr(acc, field, value)
    await session.commit()
    return User.from_model(acc)


@router.post(
    "/{user_id}/balance",
    response_model=User,
    dependencies=[Depends(require_perm("users.admin.balance.edit"))],
    summary="Manually adjust user balance",
    description="Top up (positive amount) or deduct (negative amount) the "
    "user's main or bonus balance. Logged to the audit trail.",
)
async def adjust_balance(
    request: Request,
    user_id: int,
    body: BalanceAdjust,
    session: AsyncSession = Depends(get_db_session),
    caller: UserModel = Depends(require_perm("users.admin.balance.edit")),
) -> User:
    acc = await _get_user(session, user_id)
    if acc.role and acc.role.key == "owner":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "the owner's balance cannot be adjusted"
        )
    field = "balance" if body.kind == "main" else "bonus_balance"
    current: Decimal = getattr(acc, field)
    new_value = current + body.amount
    if new_value < 0:
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, "insufficient funds")
    setattr(acc, field, new_value)
    await audit(
        session,
        action="user.balance.adjust",
        actor_id=caller.id,
        actor_role=caller.role.name if caller.role else None,
        target_type="user",
        target_id=str(acc.id),
        ip=request.client.host if request.client else None,
        meta={"kind": body.kind, "amount": str(body.amount), "reason": body.reason},
    )
    await session.commit()
    await session.refresh(acc)
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
