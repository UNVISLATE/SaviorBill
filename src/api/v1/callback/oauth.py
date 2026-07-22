"""Колбэк OAuth-провайдера: обмен кода через Lua, привязка аккаунта, токены."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from dependencies.auth import TokenSvc, get_token_svc
from dependencies.oauth import OAuthSvc, build_lua_request, get_oauth_svc
from dependencies.ratelimit import LimitKind, rate_limit
from models.user import UserModel
from schemas.auth import TokenPair
from schemas.oauth import OAuthPendingConfirm, OAuthPendingLink

router = APIRouter(prefix="/api/v1/callback/oauth", tags=["callback"])


@router.get(
    "/{provider}",
    response_model=None,
    summary="OAuth callback",
    description=(
        "Completes OAuth for the provider redirect. Returns `TokenPair` for "
        "the linked/created account, or `OAuthPendingLink` if the login "
        "matches an existing account by email — ownership must first be "
        "confirmed via POST /pending/{pending_token}/confirm."
    ),
    dependencies=[Depends(rate_limit("oauth.callback", LimitKind.AUTH))],
)
async def oauth_callback(
    provider: str,
    request: Request,
    code: str = Query(..., description="provider auth code"),
    state: str = Query(..., description="request state"),
    svc: OAuthSvc = Depends(get_oauth_svc),
    tokens: TokenSvc = Depends(get_token_svc),
) -> TokenPair | OAuthPendingLink:
    user, account_id = await svc.finish(
        provider, code, state, build_lua_request(request)
    )
    if account_id is not None:
        acc = await svc.s.get(UserModel, account_id)
        if acc is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "account not found")
        await svc.link_to_existing(acc, provider, user)
        await svc.s.commit()
        return tokens.issue(acc)

    acc, pending = await svc.link_account(provider, user)
    await svc.s.commit()
    if pending is not None:
        return pending
    return tokens.issue(acc)


@router.post(
    "/pending/{pending_token}/confirm",
    response_model=TokenPair,
    summary="Confirm pending OAuth link",
    description=(
        "Confirms a pending OAuth link (see OAuthPendingLink from the "
        "callback) with the code emailed to the existing account, and "
        "issues tokens for that account."
    ),
    dependencies=[Depends(rate_limit("oauth.pending_confirm", LimitKind.AUTH))],
)
async def confirm_pending_link(
    pending_token: str,
    body: OAuthPendingConfirm,
    svc: OAuthSvc = Depends(get_oauth_svc),
    tokens: TokenSvc = Depends(get_token_svc),
) -> TokenPair:
    acc = await svc.confirm_pending_link(pending_token, body.code)
    await svc.s.commit()
    return tokens.issue(acc)


__all__ = ["router"]
