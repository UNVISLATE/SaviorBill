"""Привязки OAuth текущего пользователя (/api/v1/user/oauth)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.auth import get_current_acc
from dependencies.db import get_db_session
from models.oauth_conn import OAuthConn
from models.user import Account
from schemas.oauth import ConnOut

router = APIRouter()


@router.get("/oauth", response_model=list[ConnOut], summary="Мои OAuth-привязки")
async def my_connections(
    acc: Account = Depends(get_current_acc),
    session: AsyncSession = Depends(get_db_session),
) -> list[OAuthConn]:
    """Список внешних учёток, привязанных к текущему аккаунту."""
    rows = await session.scalars(
        select(OAuthConn).where(OAuthConn.account_id == acc.id).order_by(OAuthConn.id)
    )
    return list(rows)


@router.delete(
    "/oauth/{provider}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Отвязать провайдера",
)
async def unlink(
    provider: str,
    acc: Account = Depends(get_current_acc),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """Удалить привязку внешней учётки у текущего аккаунта."""
    conn = await session.scalar(
        select(OAuthConn).where(
            OAuthConn.account_id == acc.id, OAuthConn.provider == provider
        )
    )
    if conn is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "привязка не найдена")
    await session.delete(conn)
    await session.commit()


__all__ = ["router"]
