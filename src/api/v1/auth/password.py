"""Сброс пароля по email-коду (/api/v1/auth/password)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from dependencies.password import ResetSvc, get_reset_svc
from dependencies.ratelimit import LimitKind, rate_limit
from schemas.auth import PassResetConfirm, PassResetRequest

router = APIRouter()


@router.post(
    "/password/reset/request",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Request password reset",
    description="Sends a 6-digit reset code if the account exists. Always returns 202.",
    dependencies=[Depends(rate_limit("password.reset.request", LimitKind.MAIL))],
)
async def request_reset(
    body: PassResetRequest,
    svc: ResetSvc = Depends(get_reset_svc),
) -> dict:
    """Запросить код сброса пароля.

    :arg body: тело с полем ``email`` (обязательно).
    :return: статус отправки.
    """
    await svc.request(body.email)
    await svc.s.commit()
    return {"status": "sent"}


@router.post(
    "/password/reset/confirm",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Confirm password reset",
    description="Sets a new password using email and the reset code.",
    dependencies=[Depends(rate_limit("password.reset.confirm", LimitKind.MAIL))],
)
async def confirm_reset(
    body: PassResetConfirm,
    svc: ResetSvc = Depends(get_reset_svc),
) -> None:
    """Подтвердить сброс пароля кодом.

    :arg body: ``email``, ``code`` (6 цифр) и новый ``password`` — все обязательны.
    """
    await svc.confirm(body.email, body.code, body.password)
    await svc.s.commit()


__all__ = ["router"]
