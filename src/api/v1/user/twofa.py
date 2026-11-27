"""Второй фактор текущего пользователя (/api/v1/user/me/2fa)."""

from __future__ import annotations

import hmac

import valkey.asyncio as valkey
from fastapi import APIRouter, Depends, HTTPException, Request, status

from dependencies.auth import get_acc_mngr, get_current_acc, get_token_svc
from dependencies.email import get_email_sender
from dependencies.rbac import require_perm
from dependencies.ratelimit import LimitKind, rate_limit
from dependencies.sec import make_secbox
from dependencies.settings import SystemSettingsMngr, get_settings_mngr
from dependencies.valkey import get_valkey_client
from lifecycle.notifications import EmailSender
from models.account_email_history import AccountEmailHistoryMngr
from models.user import UserMngr, UserModel
from schemas.auth import (
    TwoFAConfirm,
    TwoFADisable,
    TwoFAEmailResetConfirm,
    TwoFAEnabled,
    TwoFASetup,
    TwoFAStatus,
)
from security.sec.crypt import generate_numeric_code
from services.auth import TokenSvc
from services.twofa import TotpSvc

router = APIRouter()

_TWOFA_EMAIL_RESET_KEY = "2fa:email_reset:"
_TWOFA_EMAIL_RESET_FAIL = "2fa:email_reset:fail:"
_MAX_EMAIL_RESET_FAILS = 5


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
    mail: EmailSender = Depends(get_email_sender),
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
        email_configured=mail.configured,
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
    description="Requires a valid TOTP code or recovery code. Revokes all active sessions.",
    dependencies=[Depends(require_perm("user.profile.edit"))],
)
async def twofa_disable(
    request: Request,
    body: TwoFADisable,
    acc: UserModel = Depends(get_current_acc),
    mngr: UserMngr = Depends(get_acc_mngr),
    tokens: TokenSvc = Depends(get_token_svc),
) -> None:
    if not acc.totp_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "two-factor is not enabled")
    svc = _svc(request)
    if not body.code or not svc.verify_any(acc, body.code):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid 2FA or recovery code")
    svc.disable(acc)
    await mngr.s.commit()
    await tokens.revoke_all_sessions(acc.id)


@router.post(
    "/me/2fa/email-reset/request",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Request 2FA reset code via verified email",
    dependencies=[
        Depends(require_perm("user.profile.edit")),
        Depends(rate_limit("mail.2fa_reset.request", LimitKind.MAIL, require_auth=True)),
    ],
)
async def twofa_email_reset_request(
    acc: UserModel = Depends(get_current_acc),
    mngr: UserMngr = Depends(get_acc_mngr),
    settings: SystemSettingsMngr = Depends(get_settings_mngr),
    vk: valkey.Valkey = Depends(get_valkey_client),
    sender: EmailSender = Depends(get_email_sender),
) -> dict:
    if not acc.totp_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "two-factor is not enabled")
    if not await settings.get_bool("auth.2fa.email_reset_enabled", False):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "2FA email reset is disabled")
    target_email = await AccountEmailHistoryMngr(mngr.s).resolve_security_email(
        acc, settings
    )
    if not target_email:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "verified email is required for 2FA reset"
        )
    if not sender.configured:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "email sending is not configured")

    digits = await settings.get_int("mail.code_digits", 6)
    ttl = await settings.get_int("mail.code_ttl", 600)
    code = generate_numeric_code(digits)
    await vk.set(_TWOFA_EMAIL_RESET_KEY + str(acc.id), code, ex=ttl)
    await vk.delete(_TWOFA_EMAIL_RESET_FAIL + str(acc.id))

    await sender.mail.send(
        target_email,
        "Сброс двухфакторной аутентификации (2FA)",
        f"Код подтверждения для сброса 2FA: {code}\n"
        f"Код действителен {max(1, ttl // 60)} мин. Если это были не вы, смените пароль.",
    )
    return {"status": "sent"}


@router.post(
    "/me/2fa/email-reset/confirm",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Confirm 2FA reset via emailed code",
    dependencies=[
        Depends(require_perm("user.profile.edit")),
        Depends(rate_limit("mail.2fa_reset.confirm", LimitKind.MAIL, require_auth=True)),
    ],
)
async def twofa_email_reset_confirm(
    request: Request,
    body: TwoFAEmailResetConfirm,
    acc: UserModel = Depends(get_current_acc),
    mngr: UserMngr = Depends(get_acc_mngr),
    settings: SystemSettingsMngr = Depends(get_settings_mngr),
    vk: valkey.Valkey = Depends(get_valkey_client),
    tokens: TokenSvc = Depends(get_token_svc),
) -> None:
    if not acc.totp_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "two-factor is not enabled")
    if not await settings.get_bool("auth.2fa.email_reset_enabled", False):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "2FA email reset is disabled")

    key = _TWOFA_EMAIL_RESET_KEY + str(acc.id)
    stored = await vk.get(key)
    if stored is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "code not requested or expired"
        )
    if not hmac.compare_digest(str(stored), body.code.strip()):
        fails = await vk.incr(_TWOFA_EMAIL_RESET_FAIL + str(acc.id))
        if fails >= _MAX_EMAIL_RESET_FAILS:
            await vk.delete(key)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid code")

    await vk.delete(key)
    await vk.delete(_TWOFA_EMAIL_RESET_FAIL + str(acc.id))
    _svc(request).disable(acc)
    await mngr.s.commit()
    await tokens.revoke_all_sessions(acc.id)


__all__ = ["router"]
