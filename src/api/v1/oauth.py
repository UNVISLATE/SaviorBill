"""Публичный OAuth: список включённых провайдеров и старт авторизации."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.db import get_db_session
from dependencies.oauth import OAuthSvc, get_oauth_svc
from models.oauth_providers import OAuthProvidersModel
from schemas.oauth import OAuthStart, Provider

router = APIRouter(prefix="/api/v1/oauth", tags=["oauth"])


@router.get(
    "/providers",
    response_model=list[Provider],
    summary="Доступные OAuth-провайдеры",
    description="Список включённых провайдеров, которыми можно войти прямо сейчас.",
)
async def providers(
    session: AsyncSession = Depends(get_db_session),
) -> list[Provider]:
    rows = await session.scalars(
        select(OAuthProvidersModel)
        .where(OAuthProvidersModel.enabled.is_(True))
        .order_by(OAuthProvidersModel.id)
    )
    return [Provider(slug=r.slug, title=r.title) for r in rows]


@router.get(
    "/{provider}",
    response_model=OAuthStart,
    summary="Старт OAuth-авторизации",
    description="Готовит state и возвращает authorize_url для редиректа на провайдера.",
)
async def start(provider: str, svc: OAuthSvc = Depends(get_oauth_svc)) -> OAuthStart:
    return await svc.start(provider)


__all__ = ["router"]
