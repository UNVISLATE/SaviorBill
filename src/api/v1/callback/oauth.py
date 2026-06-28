"""Колбэк OAuth-провайдера: обмен кода, привязка аккаунта, выдача токенов."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from dependencies.auth import TokenSvc, get_token_svc
from dependencies.oauth import OAuthSvc, get_oauth_svc
from schemas.auth import TokenPair

router = APIRouter(prefix="/api/v1/callback/oauth", tags=["callback"])


@router.get(
    "/{provider}",
    response_model=TokenPair,
    summary="Колбэк OAuth",
    description=(
        "Принимает редирект провайдера (code + state), обменивает код на профиль, "
        "находит/создаёт аккаунт и выдаёт пару токенов. Email из провайдера с "
        "подтверждением автоматически верифицирует аккаунт."
    ),
)
async def oauth_callback(
    provider: str,
    code: str = Query(...),
    state: str = Query(...),
    svc: OAuthSvc = Depends(get_oauth_svc),
    tokens: TokenSvc = Depends(get_token_svc),
) -> TokenPair:
    user = await svc.finish(provider, code, state)
    acc = await svc.link_account(provider, user)
    await svc.s.commit()
    return tokens.issue(acc)


__all__ = ["router"]
