"""Верификация email текущего пользователя (/api/v1/user/me/verify)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from dependencies.auth import get_current_acc
from dependencies.mail import VerifySvc, get_verify_svc
from dependencies.ratelimit import LimitKind, rate_limit
from models.user import UserModel
from schemas.auth import Account, EmailVerifyConfirm

router = APIRouter()


@router.post(
    "/me/verify/email/request",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Запросить подтверждение email",
    description=(
        "Отправляет на email аккаунта 4-значный код подтверждения с ограниченным "
        "временем жизни. Если SMTP не настроен — возвращает 404."
    ),
    dependencies=[Depends(rate_limit("mail.verify.request", LimitKind.MAIL))],
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
    summary="Подтвердить email",
    description="Подтверждает email по 4-значному коду из письма (код в теле).",
    dependencies=[Depends(rate_limit("mail.verify.confirm", LimitKind.MAIL))],
)
async def confirm_email(
    body: EmailVerifyConfirm,
    acc: UserModel = Depends(get_current_acc),
    svc: VerifySvc = Depends(get_verify_svc),
) -> Account:
    """Подтвердить email текущего пользователя по коду.

    :arg body: тело с полем ``code`` (4 цифры, обязательно).
    :arg acc: текущий аутентифицированный аккаунт.
    :return: обновлённый профиль аккаунта.
    """
    acc = await svc.confirm_email(acc, body.code)
    await svc.s.commit()
    return Account.from_account(acc)


__all__ = ["router"]
