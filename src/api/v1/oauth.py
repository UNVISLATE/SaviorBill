"""Публичный OAuth: список включённых провайдеров и старт авторизации."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.db import get_db_session
from dependencies.oauth import OAuthSvc, get_oauth_svc
from models.oauth_cfg import OAuthCfg
from schemas.oauth import OAuthStartOut, ProviderOut

router = APIRouter(prefix="/api/v1/oauth", tags=["oauth"])


@router.get(
    "/providers",
    response_model=list[ProviderOut],
    summary="Доступные OAuth-провайдеры",
    description="Список включённых провайдеров, которыми можно войти прямо сейчас.",
)
async def providers(
    session: AsyncSession = Depends(get_db_session),
) -> list[ProviderOut]:
    rows = await session.scalars(
        select(OAuthCfg).where(OAuthCfg.enabled.is_(True)).order_by(OAuthCfg.id)
    )
    return [ProviderOut(slug=r.slug, title=r.title) for r in rows]


@router.get(
    "/{provider}",
    response_model=OAuthStartOut,
    summary="Старт OAuth-авторизации",
    description="Готовит state и возвращает authorize_url для редиректа на провайдера.",
)
async def start(
    provider: str, svc: OAuthSvc = Depends(get_oauth_svc)
) -> OAuthStartOut:
    return await svc.start(provider)


__all__ = ["router"]
