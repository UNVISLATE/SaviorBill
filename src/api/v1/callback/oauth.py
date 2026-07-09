"""Колбэк OAuth-провайдера: обмен кода через Lua, привязка аккаунта, токены."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from dependencies.auth import TokenSvc, get_token_svc
from dependencies.oauth import OAuthSvc, build_lua_request, get_oauth_svc
from models.user import UserModel
from schemas.auth import TokenPair

router = APIRouter(prefix="/api/v1/callback/oauth", tags=["callback"])


@router.get(
    "/{provider}",
    response_model=TokenPair,
    summary="OAuth callback",
    description="Completes OAuth for the provider redirect and returns tokens for the linked or created account.",
)
async def oauth_callback(
    provider: str,
    request: Request,
    code: str = Query(..., description="provider auth code"),
    state: str = Query(..., description="request state"),
    svc: OAuthSvc = Depends(get_oauth_svc),
    tokens: TokenSvc = Depends(get_token_svc),
) -> TokenPair:
    user, account_id = await svc.finish(
        provider, code, state, build_lua_request(request)
    )
    if account_id is not None:
        acc = await svc.s.get(UserModel, account_id)
        if acc is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "account not found")
        await svc.link_to_existing(acc, provider, user)
    else:
        acc = await svc.link_account(provider, user)
    await svc.s.commit()
    return tokens.issue(acc)


__all__ = ["router"]
