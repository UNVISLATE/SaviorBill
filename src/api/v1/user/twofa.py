"""Второй фактор текущего пользователя (/api/v1/user/me/2fa)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from dependencies.auth import get_acc_mngr, get_current_acc, get_token_svc
from dependencies.rbac import require_perm
from dependencies.sec import make_secbox
from dependencies.settings import SystemSettingsMngr, get_settings_mngr
from models.user import UserMngr, UserModel
from schemas.auth import (
    TwoFAConfirm,
    TwoFADisable,
    TwoFAEnabled,
    TwoFASetup,
    TwoFAStatus,
)
from security.sec.pwd import verify_pass
from services.auth import TokenSvc
from services.twofa import TotpSvc

router = APIRouter()


def _svc(request: Request) -> TotpSvc:
    return TotpSvc(make_secbox(request.app.state.settings))


@router.get(
    "/me/2fa",
    response_model=TwoFAStatus,
    summary="Two-factor status",
    dependencies=[Depends(require_perm("user.profile.read"))],
)
async def twofa_status(
    acc: UserModel = Depends(get_current_acc),
    settings: SystemSettingsMngr = Depends(get_settings_mngr),
) -> TwoFAStatus:
    required = bool(
        acc.role
        and acc.role.admin_login_allowed
        and await settings.get_bool("auth.2fa.required_for_admin", False)
    )
    return TwoFAStatus(
        enabled=acc.totp_enabled,
        required=required,
        recovery_codes_left=len(acc.totp_recovery or []),
    )


@router.post(
    "/me/2fa/setup",
    response_model=TwoFASetup,
    summary="Start two-factor setup",
    description="Issues a fresh TOTP secret. Two-factor stays off until it is "
    "confirmed with a code from the authenticator.",
    dependencies=[Depends(require_perm("user.profile.edit"))],
)
async def twofa_setup(
    request: Request,
    acc: UserModel = Depends(get_current_acc),
    mngr: UserMngr = Depends(get_acc_mngr),
    settings: SystemSettingsMngr = Depends(get_settings_mngr),
) -> TwoFASetup:
    if acc.totp_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "two-factor is already enabled")
    issuer = await settings.get("ui.admin.name")
    secret, uri = _svc(request).start_enrollment(acc, issuer)
    await mngr.s.commit()
    return TwoFASetup(secret=secret, otpauth_url=uri)


@router.post(
    "/me/2fa/enable",
    response_model=TwoFAEnabled,
    summary="Confirm and enable two-factor",
    description="Recovery codes are returned once and never again — store them.",
    dependencies=[Depends(require_perm("user.profile.edit"))],
)
async def twofa_enable(
    request: Request,
    body: TwoFAConfirm,
    acc: UserModel = Depends(get_current_acc),
    mngr: UserMngr = Depends(get_acc_mngr),
    tokens: TokenSvc = Depends(get_token_svc),
) -> TwoFAEnabled:
    try:
        codes = _svc(request).enable(acc, body.code)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid code") from exc
    await mngr.s.commit()
    # Сессии, выданные до появления второго фактора, его не проходили.
    await tokens.revoke_all_sessions(acc.id)
    return TwoFAEnabled(recovery_codes=codes)


@router.post(
    "/me/2fa/disable",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Disable two-factor",
    description="Requires the current password (or a code, for accounts without "
    "a password).",
    dependencies=[Depends(require_perm("user.profile.edit"))],
)
async def twofa_disable(
    request: Request,
    body: TwoFADisable,
    acc: UserModel = Depends(get_current_acc),
    mngr: UserMngr = Depends(get_acc_mngr),
) -> None:
    if not acc.totp_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "two-factor is not enabled")
    svc = _svc(request)
    confirmed = (
        verify_pass(acc.pass_hash, body.password)
        if acc.has_pass and body.password
        else bool(body.code) and svc.verify_any(acc, body.code or "")
    )
    if not confirmed:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "confirmation failed")
    svc.disable(acc)
    await mngr.s.commit()


__all__ = ["router"]
