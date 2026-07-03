"""Админ: пользователи, их услуги, платежи и OAuth-привязки."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.db import get_db_session
from dependencies.rbac import require_perm
from models.user import UserModel
from models.user_oauth import UserOauthModel, UserOauthMngr
from models.user_payments import UserPaymentsModel
from models.user_services import UserServicesModel
from schemas.orders import OrderAdmin
from schemas.page import Page
from schemas.payments import PaymentAdmin
from schemas.user import OAuthConnAdmin, User, UserDetail, UserPatch
from utils.pagination import PageParams, page_params, paginate
from utils.apidoc import with_fields

router = APIRouter()


async def _get_user(session: AsyncSession, user_id: int) -> UserModel:
    """Загрузить аккаунт или вернуть 404.

    :arg session: сессия БД; :arg user_id: id аккаунта.
    :return: модель аккаунта.
    """
    acc = await session.get(UserModel, user_id)
    if acc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "пользователь не найден")
    return acc


@router.get(
    "/users",
    response_model=Page[User],
    dependencies=[Depends(require_perm("users.read"))],
    summary="Список пользователей",
    description="Постранично. Требует право users.read.",
)
async def list_users(
    pp: PageParams = Depends(page_params),
    session: AsyncSession = Depends(get_db_session),
) -> Page[User]:
    """Постраничный список аккаунтов."""
    stmt = select(UserModel).order_by(UserModel.id)
    items, total, has_more = await paginate(
        session, stmt, User.from_model, limit=pp.limit, offset=pp.offset
    )
    return Page(
        items=items, total=total, limit=pp.limit, offset=pp.offset, has_more=has_more
    )


@router.get(
    "/users/{user_id}",
    response_model=UserDetail,
    dependencies=[Depends(require_perm("users.read"))],
    summary="Карточка пользователя",
    description=(
        "Полная информация о пользователе: профиль, роль, OAuth-привязки и "
        "счётчики услуг/платежей. Требует право users.read."
    ),
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


@router.patch(
    "/users/{user_id}",
    response_model=User,
    dependencies=[Depends(require_perm("users.edit"))],
    summary="Редактировать пользователя",
    description=with_fields(
        "Меняет только переданные поля (email, активность, роль, балансы).",
        UserPatch,
    ),
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
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(acc, field, value)
    await session.commit()
    return User.from_model(acc)


@router.get(
    "/users/{user_id}/services",
    response_model=Page[OrderAdmin],
    dependencies=[Depends(require_perm("orders.read"))],
    summary="Услуги пользователя",
    description="Выданные услуги пользователя с приватными данными. Право orders.read.",
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
    "/users/{user_id}/orders",
    response_model=Page[OrderAdmin],
    dependencies=[Depends(require_perm("orders.read"))],
    summary="Заказы пользователя",
    description="Алиас услуг пользователя (для поддержки). Право orders.read.",
)
async def user_orders(
    user_id: int,
    pp: PageParams = Depends(page_params),
    session: AsyncSession = Depends(get_db_session),
) -> Page[OrderAdmin]:
    """Список заказов пользователя (совпадает с услугами)."""
    return await user_services(user_id, pp, session)


@router.get(
    "/users/{user_id}/payments",
    response_model=Page[PaymentAdmin],
    dependencies=[Depends(require_perm("purchases.read"))],
    summary="Платежи пользователя",
    description="Все платежи пользователя с приватными данными. Право purchases.read.",
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
    "/users/{user_id}/oauth",
    response_model=list[OAuthConnAdmin],
    dependencies=[Depends(require_perm("users.read"))],
    summary="OAuth-привязки пользователя",
    description="Внешние OAuth-учётки, привязанные к аккаунту. Право users.read.",
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


__all__ = ["router"]
