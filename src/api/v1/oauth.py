"""Публичный OAuth: список включённых провайдеров и старт авторизации."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.db import get_db_session
from dependencies.oauth import OAuthSvc, get_oauth_svc
from dependencies.ratelimit import LimitKind, rate_limit
from models.oauth_providers import OAuthProvidersModel
from schemas.oauth import OAuthStart, Provider

router = APIRouter(prefix="/api/v1/oauth", tags=["oauth"])


def _icon_url(token: str | None) -> str | None:
    return f"/api/media/{token}" if token else None


@router.get(
    "/providers",
    response_model=list[Provider],
    summary="Available OAuth providers",
    description="Enabled providers available for sign-in.",
)
async def providers(
    session: AsyncSession = Depends(get_db_session),
) -> list[Provider]:
    rows = await session.scalars(
        select(OAuthProvidersModel)
        .where(OAuthProvidersModel.enabled.is_(True))
        .order_by(OAuthProvidersModel.id)
    )
    return [
        Provider(
            slug=r.slug,
            title=r.title,
            icon_url=_icon_url(r.icon.token if r.icon else None),
        )
        for r in rows
    ]


@router.get(
    "/{provider}",
    response_model=OAuthStart,
    summary="Start OAuth sign-in",
    description="Creates state and returns authorize_url for provider redirect.",
    dependencies=[Depends(rate_limit("oauth.start", LimitKind.AUTH))],
)
async def start(
    provider: str, request: Request, svc: OAuthSvc = Depends(get_oauth_svc)
) -> OAuthStart:
    return await svc.start(provider, request=request)


__all__ = ["router"]
