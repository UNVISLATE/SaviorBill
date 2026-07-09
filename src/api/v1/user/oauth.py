"""Привязки OAuth текущего пользователя (/api/v1/user/oauth)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.auth import get_current_acc
from dependencies.db import get_db_session
from dependencies.oauth import OAuthSvc, get_oauth_svc
from dependencies.rbac import require_perm
from models.user import UserModel
from models.user_oauth import UserOauthModel
from schemas.oauth import Conn, OAuthStart

router = APIRouter()


@router.get(
    "/oauth",
    response_model=list[Conn],
    summary="Мои OAuth-привязки",
    dependencies=[Depends(require_perm("user.oauth.read"))],
)
async def my_connections(
    acc: UserModel = Depends(get_current_acc),
    session: AsyncSession = Depends(get_db_session),
) -> list[Conn]:
    """Список внешних учёток, привязанных к текущему аккаунту."""
    rows = await session.scalars(
        select(UserOauthModel)
        .where(UserOauthModel.account_id == acc.id)
        .order_by(UserOauthModel.id)
    )
    return [Conn.from_model(r) for r in rows]


@router.get(
    "/oauth/{provider}/link",
    response_model=OAuthStart,
    summary="Привязать провайдера к моему аккаунту",
    description=(
        "Старт OAuth для привязки внешней учётки к ТЕКУЩЕМУ аккаунту. Возвращает "
        "authorize_url для редиректа; после колбэка учётка привяжется к вам."
    ),
    dependencies=[Depends(require_perm("user.oauth.edit"))],
)
async def link_start(
    provider: str,
    request: Request,
    acc: UserModel = Depends(get_current_acc),
    svc: OAuthSvc = Depends(get_oauth_svc),
) -> OAuthStart:
    """Инициировать привязку провайдера к вошедшему аккаунту."""
    return await svc.start(provider, account_id=acc.id, request=request)


@router.delete(
    "/oauth/{provider}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Отвязать провайдера",
    dependencies=[Depends(require_perm("user.oauth.edit"))],
)
async def unlink(
    provider: str,
    acc: UserModel = Depends(get_current_acc),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """Удалить привязку внешней учётки у текущего аккаунта."""
    conn = await session.scalar(
        select(UserOauthModel).where(
            UserOauthModel.account_id == acc.id, UserOauthModel.provider == provider
        )
    )
    if conn is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "привязка не найдена")
    await session.delete(conn)
    await session.commit()


__all__ = ["router"]
