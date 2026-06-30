"""Сброс пароля по email (/api/v1/auth/password)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from dependencies.password import ResetSvc, get_reset_svc
from dependencies.ratelimit import LimitKind, rate_limit
from schemas.auth import PassResetConfirm, PassResetRequest

router = APIRouter()


@router.post(
    "/password/reset/request",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Запросить сброс пароля",
    description=(
        "Отправляет письмо со ссылкой сброса, если аккаунт с таким email "
        "существует. Ответ всегда 202 (не раскрывает наличие аккаунта)."
    ),
    dependencies=[Depends(rate_limit("password.reset.request", LimitKind.MAIL))],
)
async def request_reset(
    body: PassResetRequest,
    svc: ResetSvc = Depends(get_reset_svc),
) -> dict:
    await svc.request(body.email)
    await svc.s.commit()
    return {"status": "sent"}


@router.post(
    "/password/reset/confirm",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Подтвердить сброс пароля",
    description="Устанавливает новый пароль по одноразовому токену из письма.",
    dependencies=[Depends(rate_limit("password.reset.confirm", LimitKind.MAIL))],
)
async def confirm_reset(
    body: PassResetConfirm,
    svc: ResetSvc = Depends(get_reset_svc),
) -> None:
    await svc.confirm(body.token, body.password)
    await svc.s.commit()


__all__ = ["router"]
