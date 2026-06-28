"""Колбэк платёжной системы (вебхук/возврат) — обработка через скрипт провайдера."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from dependencies.payment import PayMngr, get_pay_mngr
from schemas.payments import PaymentOut

router = APIRouter(prefix="/api/v1/callback/payment", tags=["callback"])


async def _request_data(request: Request) -> dict:
    """Собрать данные платёжки: query-параметры + тело (json/form), как есть."""
    data: dict = dict(request.query_params)
    try:
        body = await request.json()
        if isinstance(body, dict):
            data.update(body)
            return data
    except Exception:  # noqa: BLE001 — не JSON, пробуем форму
        pass
    try:
        form = await request.form()
        data.update({k: v for k, v in form.items()})
    except Exception:  # noqa: BLE001 — пустое/нечитаемое тело
        pass
    return data


@router.post(
    "/{provider}",
    response_model=PaymentOut,
    summary="Колбэк оплаты (webhook)",
    description=(
        "Точка вебхука платёжки. Данные запроса (query + тело) передаются в "
        "callback-скрипт провайдера, который проверяет подпись/секреты и "
        "определяет результат. Идемпотентно."
    ),
)
async def payment_callback(
    provider: str,
    request: Request,
    svc: PayMngr = Depends(get_pay_mngr),
) -> PaymentOut:
    data = await _request_data(request)
    payment = await svc.callback(provider, data)
    await svc.s.commit()
    return payment


@router.get(
    "/{provider}",
    response_model=PaymentOut,
    summary="Колбэк оплаты (возврат success/fail)",
    description="GET-вариант для платёжек, возвращающих пользователя на URL.",
)
async def payment_return(
    provider: str,
    request: Request,
    svc: PayMngr = Depends(get_pay_mngr),
) -> PaymentOut:
    data = await _request_data(request)
    payment = await svc.callback(provider, data)
    await svc.s.commit()
    return payment


__all__ = ["router"]
