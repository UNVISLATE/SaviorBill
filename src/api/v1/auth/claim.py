"""Эндпоинты клейма гостевых аккаунтов (/api/v1/auth/claim-guest-account/*)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response, status

from dependencies.auth import TokenSvc, get_token_svc
from dependencies.guest_checkout import GuestCheckoutSvc, get_guest_checkout_svc
from dependencies.login_guard import client_ip
from dependencies.ratelimit import LimitKind, rate_limit
from schemas.auth import TokenPair
from schemas.guest import GuestClaimRequest, GuestClaimRequestResult, GuestClaimVerify
from security.sec.cookies import set_auth_cookies

router = APIRouter()


@router.post(
    "/claim-guest-account/request",
    response_model=GuestClaimRequestResult,
    status_code=status.HTTP_200_OK,
    summary="Request OTP code to claim guest account",
    description="Sends a 6-digit confirmation code to the guest email address.",
    dependencies=[Depends(rate_limit("auth.guest_claim.request", LimitKind.MAIL))],
)
async def request_claim_code(
    body: GuestClaimRequest,
    svc: GuestCheckoutSvc = Depends(get_guest_checkout_svc),
) -> GuestClaimRequestResult:
    """Запросить код подтверждения на email гостевого аккаунта."""
    claim_token, ttl = await svc.request_guest_claim(body.email)
    await svc.s.commit()
    return GuestClaimRequestResult(claim_token=claim_token, ttl_seconds=ttl)


@router.post(
    "/claim-guest-account/verify",
    response_model=TokenPair,
    status_code=status.HTTP_200_OK,
    summary="Verify OTP code and activate guest account",
    description="Validates the OTP code, sets a password, promotes role to user, and issues auth tokens.",
    dependencies=[Depends(rate_limit("auth.guest_claim.verify", LimitKind.AUTH))],
)
async def verify_claim_code(
    body: GuestClaimVerify,
    request: Request,
    response: Response,
    svc: GuestCheckoutSvc = Depends(get_guest_checkout_svc),
    tokens: TokenSvc = Depends(get_token_svc),
) -> TokenPair:
    """Подтвердить владение гостевым аккаунтом, задать пароль и войти."""
    acc = await svc.verify_guest_claim(body.claim_token, body.code, body.password)
    await svc.s.commit()

    pair = await tokens.issue_tracked(
        acc, ip=client_ip(request), user_agent=request.headers.get("user-agent")
    )
    set_auth_cookies(
        response, tokens.cfg, access_token=pair.access_token, refresh_token=pair.refresh_token
    )
    return pair


__all__ = ["router"]
