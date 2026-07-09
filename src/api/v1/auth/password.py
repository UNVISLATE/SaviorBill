"""Сброс пароля по email-коду/токену (/api/v1/auth/password).

Способ управляется настройкой ``password.reset.method``: ``code``/``token`` —
email-сброс включён; ``authenticated``/``disabled`` — email-сброс выключен
(404 на request/confirm), при ``authenticated`` доступна только смена пароля
в профиле по старому паролю (``POST /me/password``).
"""

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
    description="Sends a reset code or token link if the account exists "
    "(mode via `password.reset.method`). Returns 404 if email-based reset "
    "is disabled by that setting, otherwise always 202.",
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
    description="Sets a new password using the reset code/token from the "
    "email. `email` is required for code mode; a token link may omit it.",
    dependencies=[Depends(rate_limit("password.reset.confirm", LimitKind.MAIL))],
)
async def confirm_reset(
    body: PassResetConfirm,
    svc: ResetSvc = Depends(get_reset_svc),
) -> None:
    """Подтвердить сброс пароля кодом/токеном.

    :arg body: ``code``/токен и новый ``password`` обязательны; ``email``
        обязателен в режиме кода, для ссылки-токена может быть опущен.
    """
    await svc.confirm(body.code, body.password, email=body.email)
    await svc.s.commit()


__all__ = ["router"]
