"""Верификация email текущего пользователя (/api/v1/user/me/verify)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from dependencies.auth import get_current_acc
from dependencies.mail import VerifySvc, get_verify_svc
from dependencies.rbac import require_perm
from dependencies.ratelimit import LimitKind, rate_limit
from dependencies.triggers import get_dispatcher
from automation.triggers import TriggerDispatcher, TriggerEvent
from models.user import UserModel
from models.user_oauth import UserOauthMngr
from schemas.auth import Account, EmailVerifyConfirm

router = APIRouter()


@router.post(
    "/me/verify/email/request",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Request email verification",
    description="Sends a short-lived verification code to the account email.",
    dependencies=[
        Depends(require_perm("user.profile.edit")),
        Depends(rate_limit("mail.verify.request", LimitKind.MAIL)),
    ],
)
async def request_email(
    acc: UserModel = Depends(get_current_acc),
    svc: VerifySvc = Depends(get_verify_svc),
) -> dict:
    """Запросить код подтверждения email.

    :arg acc: текущий аутентифицированный аккаунт.
    :return: статус отправки.
    """
    await svc.request_email(acc)
    return {"status": "sent"}


@router.post(
    "/me/verify/email/confirm",
    response_model=Account,
    summary="Confirm email",
    description="Confirms the account email using the code from the message.",
    dependencies=[
        Depends(require_perm("user.profile.edit")),
        Depends(rate_limit("mail.verify.confirm", LimitKind.MAIL)),
    ],
)
async def confirm_email(
    body: EmailVerifyConfirm,
    acc: UserModel = Depends(get_current_acc),
    svc: VerifySvc = Depends(get_verify_svc),
    triggers: TriggerDispatcher = Depends(get_dispatcher),
) -> Account:
    """Подтвердить email текущего пользователя по коду.

    :arg body: тело с полем ``code`` (числовой код, длина настраивается).
    :arg acc: текущий аутентифицированный аккаунт.
    :return: обновлённый профиль аккаунта.
    """
    acc = await svc.confirm_email(acc, body.code)
    await svc.s.commit()
    await triggers.fire(
        TriggerEvent.USER_VERIFIED,
        {"user": {"id": acc.id, "login": acc.login, "email": acc.email}},
    )
    conns = await UserOauthMngr(svc.s).list_for_account(acc.id)
    return Account.from_account(acc, oauth_providers=[c.provider for c in conns])


__all__ = ["router"]
