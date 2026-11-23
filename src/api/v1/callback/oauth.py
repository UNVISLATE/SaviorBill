"""Колбэк OAuth-провайдера: обмен кода через Lua, привязка аккаунта, токены."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse

from dependencies.auth import TokenSvc, get_token_svc
from dependencies.oauth import OAuthSvc, build_lua_request, get_oauth_svc
from dependencies.ratelimit import LimitKind, rate_limit
from errors import AuthSessionLimitError
from models.user import UserModel
from schemas.auth import TokenPair
from schemas.oauth import OAuthPendingConfirm, OAuthPendingLink
from security.sec.cookies import set_auth_cookies

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
    response: Response,
    code: str = Query(..., description="provider auth code"),
    state: str = Query(..., description="request state"),
    svc: OAuthSvc = Depends(get_oauth_svc),
    tokens: TokenSvc = Depends(get_token_svc),
) -> TokenPair | OAuthPendingLink | RedirectResponse:
    user, account_id = await svc.finish(
        provider, code, state, build_lua_request(request)
    )
    return_url = getattr(svc, "last_return_url", None)
    ua = request.headers.get("user-agent")
    ip = request.client.host if request.client else None
    if account_id is not None:
        acc = await svc.s.get(UserModel, account_id)
        if acc is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "account not found")
        await svc.link_to_existing(acc, provider, user)
        await svc.s.commit()
        try:
            pair = await tokens.issue_tracked(acc, ip=ip, user_agent=ua)
        except AuthSessionLimitError:
            raise HTTPException(status.HTTP_409_CONFLICT, "active session limit reached") from None
        if return_url:
            redir = RedirectResponse(url=return_url, status_code=status.HTTP_302_FOUND)
            set_auth_cookies(
                redir,
                tokens.cfg,
                access_token=pair.access_token,
                refresh_token=pair.refresh_token,
                request=request,
            )
            return redir
        set_auth_cookies(
            response,
            tokens.cfg,
            access_token=pair.access_token,
            refresh_token=pair.refresh_token,
            request=request,
        )
        return pair

    acc, pending = await svc.link_account(provider, user)
    await svc.s.commit()
    if pending is not None:
        if return_url:
            sep = "&" if "?" in return_url else "?"
            return RedirectResponse(
                url=f"{return_url}{sep}oauth_pending={pending.pending_token}",
                status_code=status.HTTP_302_FOUND,
            )
        return pending
    try:
        pair = await tokens.issue_tracked(acc, ip=ip, user_agent=ua)
    except AuthSessionLimitError:
        raise HTTPException(status.HTTP_409_CONFLICT, "active session limit reached") from None
    if return_url:
        redir = RedirectResponse(url=return_url, status_code=status.HTTP_302_FOUND)
        set_auth_cookies(
            redir,
            tokens.cfg,
            access_token=pair.access_token,
            refresh_token=pair.refresh_token,
            request=request,
        )
        return redir
    set_auth_cookies(
        response,
        tokens.cfg,
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        request=request,
    )
    return pair


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
    request: Request,
    response: Response,
    svc: OAuthSvc = Depends(get_oauth_svc),
    tokens: TokenSvc = Depends(get_token_svc),
) -> TokenPair:
    acc = await svc.confirm_pending_link(pending_token, body.code)
    await svc.s.commit()
    try:
        pair = await tokens.issue_tracked(
            acc,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except AuthSessionLimitError:
        raise HTTPException(status.HTTP_409_CONFLICT, "active session limit reached") from None
    set_auth_cookies(
        response,
        tokens.cfg,
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        request=request,
    )
    return pair


__all__ = ["router"]
