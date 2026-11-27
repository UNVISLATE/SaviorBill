"""Колбэк OAuth-провайдера: обмен кода через Lua, привязка аккаунта, токены."""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from dependencies.auth import TokenSvc, get_token_svc
from dependencies.oauth import OAuthSvc, build_lua_request, get_oauth_svc
from dependencies.ratelimit import LimitKind, rate_limit
from errors import AuthSessionLimitError
from models.user import UserModel
from schemas.auth import TokenPair
from schemas.oauth import OAuthPendingConfirm, OAuthPendingLink
from dependencies.sec import make_secbox
from security.sec.cookies import set_auth_cookies
from services.twofa import TotpSvc

router = APIRouter(prefix="/api/v1/callback/oauth", tags=["callback"])

_OAUTH_2FA_TTL = 300


class OAuthTwoFaConfirm(BaseModel):
    challenge_token: str = Field(..., min_length=8, max_length=256)
    code: str = Field(..., min_length=4, max_length=32)


def _assert_login_allowed(acc: UserModel) -> None:
    if acc.role is not None and not acc.role.allow_login:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "login not allowed for this role"
        )


async def _issue_2fa_challenge(
    svc: OAuthSvc, acc: UserModel, return_url: str | None
) -> RedirectResponse:
    token = secrets.token_urlsafe(32)
    vk = getattr(svc, "vk", None)
    if vk is not None:
        await vk.set(f"oauth:2fa:{token}", str(acc.id), ex=_OAUTH_2FA_TTL)
    if return_url:
        sep = "&" if "?" in return_url else "?"
        return RedirectResponse(
            url=f"{return_url}{sep}oauth_2fa_token={token}",
            status_code=status.HTTP_302_FOUND,
        )
    raise HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        "totp required",
        headers={"X-OAuth-2FA-Token": token},
    )


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
    _assert_login_allowed(acc)
    if acc.totp_enabled:
        return await _issue_2fa_challenge(svc, acc, return_url)
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
    _assert_login_allowed(acc)
    if acc.totp_enabled:
        await _issue_2fa_challenge(svc, acc, None)
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


@router.post(
    "/2fa/confirm",
    response_model=TokenPair,
    summary="Complete OAuth login with 2FA",
    dependencies=[Depends(rate_limit("oauth.2fa_confirm", LimitKind.AUTH))],
)
async def confirm_oauth_2fa(
    body: OAuthTwoFaConfirm,
    request: Request,
    response: Response,
    svc: OAuthSvc = Depends(get_oauth_svc),
    tokens: TokenSvc = Depends(get_token_svc),
) -> TokenPair:
    vk = getattr(svc, "vk", None)
    key = f"oauth:2fa:{body.challenge_token}"
    raw_id = await vk.get(key) if vk is not None else None
    if not raw_id:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "oauth 2fa challenge expired or invalid"
        )
    acc = await svc.s.get(UserModel, int(raw_id))
    if acc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "account not found")
    _assert_login_allowed(acc)
    if not TotpSvc(make_secbox(tokens.cfg)).verify_any(acc, body.code):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid totp")
    await vk.delete(key)
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
