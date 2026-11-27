"""GDPR-эндпоинты пользователя: статус, выгрузка данных и анонимизация аккаунта."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone

import valkey.asyncio as valkey
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.auth import get_acc_mngr, get_current_acc, get_token_svc
from dependencies.db import get_db_session
from dependencies.rbac import require_perm
from dependencies.sec import make_secbox
from dependencies.settings import SystemSettingsMngr, get_settings_mngr
from dependencies.valkey import get_valkey_client
from models.account_email_history import AccountEmailHistoryMngr
from models.user import UserMngr, UserModel
from models.user_oauth import UserOauthModel
from models.user_payments import UserPaymentsModel
from models.user_services import UserServicesModel
from security.owner_guard import assert_account_deletable
from security.sec.pwd import verify_pass
from services.audit import audit
from services.auth import TokenSvc
from services.twofa import TotpSvc
from utils.datetime_utils import utc_now

router = APIRouter()

_GDPR_EXPORT_RL_KEY = "gdpr:export:rl:"


class GdprStatusResponse(BaseModel):
    enabled: bool
    export_enabled: bool
    erasure_enabled: bool
    cooldown_remaining_sec: int = 0
    rate_limit_remaining_sec: int = 0
    allow_cooldown_bypass_with_2fa: bool = False


class GdprExportRequest(BaseModel):
    totp_code: str | None = Field(default=None, max_length=32)


class GdprDeleteRequest(BaseModel):
    confirm: bool = Field(..., description="Explicit confirmation of erasure")
    totp_code: str | None = Field(default=None, max_length=32)
    password: str | None = Field(default=None, max_length=128)


def _cooldown_remaining_sec(acc: UserModel, cooldown_hours: int) -> int:
    if cooldown_hours <= 0:
        return 0
    last_chg = getattr(acc, "last_security_change_at", None)
    if last_chg is None:
        return 0
    if last_chg.tzinfo is None:
        last_chg = last_chg.replace(tzinfo=timezone.utc)
    elapsed = (utc_now() - last_chg).total_seconds()
    limit = cooldown_hours * 3600
    if elapsed >= limit:
        return 0
    return max(1, int(limit - elapsed))


@router.get(
    "/me/gdpr/status",
    response_model=GdprStatusResponse,
    summary="GDPR compliance status and cooldowns",
    dependencies=[Depends(require_perm("user.profile.read"))],
)
async def gdpr_status(
    acc: UserModel = Depends(get_current_acc),
    settings: SystemSettingsMngr = Depends(get_settings_mngr),
    vk: valkey.Valkey = Depends(get_valkey_client),
) -> GdprStatusResponse:
    enabled = await settings.get_bool("gdpr.enabled", False)
    if not enabled:
        return GdprStatusResponse(
            enabled=False, export_enabled=False, erasure_enabled=False
        )
    export_enabled = await settings.get_bool("gdpr.export.enabled", False)
    erasure_enabled = await settings.get_bool("gdpr.erasure.enabled", False)
    cooldown_h = max(0, await settings.get_int("gdpr.export.security_cooldown_hours", 24))
    bypass_2fa = await settings.get_bool("gdpr.export.allow_cooldown_bypass_with_2fa", False)
    cd_rem = _cooldown_remaining_sec(acc, cooldown_h)
    rl_rem = 0
    try:
        ttl = await vk.ttl(_GDPR_EXPORT_RL_KEY + str(acc.id))
        if isinstance(ttl, int) and ttl > 0:
            rl_rem = ttl
    except Exception:  # noqa: BLE001
        rl_rem = 0
    return GdprStatusResponse(
        enabled=True,
        export_enabled=export_enabled,
        erasure_enabled=erasure_enabled,
        cooldown_remaining_sec=cd_rem,
        rate_limit_remaining_sec=rl_rem,
        allow_cooldown_bypass_with_2fa=bypass_2fa,
    )


@router.post(
    "/me/gdpr/export",
    summary="Export personal data (GDPR Art. 15/20)",
    dependencies=[Depends(require_perm("user.profile.read"))],
)
async def gdpr_export(
    request: Request,
    body: GdprExportRequest | None = None,
    acc: UserModel = Depends(get_current_acc),
    session: AsyncSession = Depends(get_db_session),
    settings: SystemSettingsMngr = Depends(get_settings_mngr),
    vk: valkey.Valkey = Depends(get_valkey_client),
):
    if not await settings.get_bool("gdpr.enabled", False) or not await settings.get_bool(
        "gdpr.export.enabled", False
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "GDPR data export is disabled")

    cooldown_h = max(0, await settings.get_int("gdpr.export.security_cooldown_hours", 24))
    cd_rem = _cooldown_remaining_sec(acc, cooldown_h)
    if cd_rem > 0:
        bypass_2fa = await settings.get_bool(
            "gdpr.export.allow_cooldown_bypass_with_2fa", False
        )
        bypassed = False
        if (
            bypass_2fa
            and acc.totp_enabled
            and body is not None
            and body.totp_code
        ):
            cfg = request.app.state.settings
            if TotpSvc(make_secbox(cfg)).verify_any(acc, body.totp_code):
                bypassed = True
        if not bypassed:
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "detail": "Export temporarily delayed after security change (email/password)",
                    "retry_after": cd_rem,
                },
                headers={"Retry-After": str(cd_rem)},
            )

    rl_hours = max(0, await settings.get_int("gdpr.export.rate_limit_hours", 24))
    rl_key = _GDPR_EXPORT_RL_KEY + str(acc.id)
    if rl_hours > 0:
        ttl = await vk.ttl(rl_key)
        if isinstance(ttl, int) and ttl > 0:
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "detail": "GDPR export rate limit active",
                    "retry_after": ttl,
                },
                headers={"Retry-After": str(ttl)},
            )

    history = await AccountEmailHistoryMngr(session).list_for_account(acc.id)
    oauth_rows = (
        await session.scalars(
            select(UserOauthModel).where(UserOauthModel.account_id == acc.id)
        )
    ).all()
    orders = (
        await session.scalars(
            select(UserServicesModel).where(UserServicesModel.account_id == acc.id)
        )
    ).all()
    payments = (
        await session.scalars(
            select(UserPaymentsModel).where(UserPaymentsModel.account_id == acc.id)
        )
    ).all()

    if rl_hours > 0:
        await vk.set(rl_key, "1", ex=rl_hours * 3600)

    await audit(
        session,
        action="user.gdpr.export",
        actor_id=acc.id,
        actor_role=acc.role.name if acc.role else None,
        target_type="user",
        target_id=str(acc.id),
        ip=request.client.host if request.client else None,
    )
    await session.commit()

    return {
        "exported_at": utc_now().isoformat(),
        "account": {
            "id": acc.id,
            "login": acc.login,
            "email": acc.email,
            "email_verified_at": acc.email_verified_at.isoformat() if acc.email_verified_at else None,
            "created_at": acc.created_at.isoformat() if acc.created_at else None,
            "balance": str(acc.balance),
            "bonus_balance": str(acc.bonus_balance),
            "totp_enabled": acc.totp_enabled,
        },
        "email_history": [
            {
                "email": h.email,
                "verified_at": h.verified_at.isoformat() if h.verified_at else None,
                "is_initial_verified": h.is_initial_verified,
                "source": h.source,
                "created_at": h.created_at.isoformat(),
            }
            for h in history
        ],
        "oauth_connections": [
            {"provider": c.provider, "email": c.email}
            for c in oauth_rows
        ],
        "orders": [
            {
                "id": o.id,
                "service_id": o.service_id,
                "status": o.status,
                "created_at": o.created_at.isoformat() if o.created_at else None,
            }
            for o in orders
        ],
        "payments": [
            {
                "id": p.id,
                "provider": p.provider,
                "amount": str(p.amount),
                "currency": p.currency,
                "status": p.status,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in payments
        ],
    }


@router.post(
    "/me/gdpr/delete",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Anonymize and deactivate account (GDPR Art. 17)",
    dependencies=[Depends(require_perm("user.profile.edit"))],
)
async def gdpr_delete(
    request: Request,
    body: GdprDeleteRequest,
    acc: UserModel = Depends(get_current_acc),
    mngr: UserMngr = Depends(get_acc_mngr),
    settings: SystemSettingsMngr = Depends(get_settings_mngr),
    tokens: TokenSvc = Depends(get_token_svc),
) -> None:
    if not await settings.get_bool("gdpr.enabled", False) or not await settings.get_bool(
        "gdpr.erasure.enabled", False
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "GDPR erasure is disabled")
    if not body.confirm:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "confirm must be true")
    assert_account_deletable(acc)

    if acc.totp_enabled:
        if not body.totp_code or not TotpSvc(make_secbox(request.app.state.settings)).verify_any(
            acc, body.totp_code
        ):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid 2FA code")
    elif acc.has_pass:
        if not body.password or not verify_pass(acc.pass_hash, body.password):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid password")

    # Анонимизация ПДн с сохранением целостности финансовых/бухгалтерских записей.
    acc.login = f"deleted_{acc.id}_{secrets.token_hex(4)}"
    acc.email = None
    acc.email_verified_at = None
    acc.pass_hash = None
    acc.totp_secret = None
    acc.totp_enabled = False
    acc.totp_recovery = []
    acc.is_active = False

    await mngr.s.execute(delete(UserOauthModel).where(UserOauthModel.account_id == acc.id))
    from models.account_email_history import AccountEmailHistoryModel

    await mngr.s.execute(
        delete(AccountEmailHistoryModel).where(AccountEmailHistoryModel.account_id == acc.id)
    )
    await audit(
        mngr.s,
        action="user.gdpr.erasure",
        actor_id=acc.id,
        actor_role=acc.role.name if acc.role else None,
        target_type="user",
        target_id=str(acc.id),
        ip=request.client.host if request.client else None,
    )
    await mngr.s.commit()
    await tokens.revoke_all_sessions(acc.id)


__all__ = ["router"]
