"""Верификация email текущего пользователя (/api/v1/user/me/verify)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status

from dependencies.auth import get_current_acc
from dependencies.mail import VerifySvc, get_verify_svc
from models.user import Account
from schemas.auth import AccOut

router = APIRouter()


@router.post(
    "/me/verify/email/request",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Запросить подтверждение email",
    description="Отправляет письмо со ссылкой подтверждения на email аккаунта.",
)
async def request_email(
    acc: Account = Depends(get_current_acc),
    svc: VerifySvc = Depends(get_verify_svc),
) -> dict:
    await svc.request_email(acc)
    return {"status": "sent"}


@router.get(
    "/me/verify/email/confirm",
    response_model=AccOut,
    summary="Подтвердить email",
    description="Подтверждает email по одноразовому токену из письма.",
)
async def confirm_email(
    token: str = Query(...),
    svc: VerifySvc = Depends(get_verify_svc),
) -> AccOut:
    acc = await svc.confirm_email(token)
    await svc.s.commit()
    return AccOut.from_account(acc)


__all__ = ["router"]
