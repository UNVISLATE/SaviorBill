"""Верификация email текущего пользователя (/api/v1/user/me/verify)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status

from dependencies.auth import get_current_acc
from dependencies.mail import VerifySvc, get_verify_svc
from dependencies.ratelimit import LimitKind, rate_limit
from models.user import UserModel
from schemas.auth import Account

router = APIRouter()


@router.post(
    "/me/verify/email/request",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Запросить подтверждение email",
    description="Отправляет письмо со ссылкой подтверждения на email аккаунта.",
    dependencies=[Depends(rate_limit("mail.verify.request", LimitKind.MAIL))],
)
async def request_email(
    acc: UserModel = Depends(get_current_acc),
    svc: VerifySvc = Depends(get_verify_svc),
) -> dict:
    await svc.request_email(acc)
    return {"status": "sent"}


@router.get(
    "/me/verify/email/confirm",
    response_model=Account,
    summary="Подтвердить email",
    description="Подтверждает email по одноразовому токену из письма.",
    dependencies=[Depends(rate_limit("mail.verify.confirm", LimitKind.MAIL))],
)
async def confirm_email(
    token: str = Query(...),
    svc: VerifySvc = Depends(get_verify_svc),
) -> Account:
    # TODO: явно обрабатывать ошибки токена; перевести на POST с кодом в теле.
    acc = await svc.confirm_email(token)
    await svc.s.commit()
    return Account.from_account(acc)


__all__ = ["router"]
