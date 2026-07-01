"""Колбэк платёжной системы (вебхук/возврат) — обработка через скрипт провайдера."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from dependencies.payment import PayMngr, get_pay_mngr
from dependencies.triggers import get_dispatcher
from enums import PayStatus, PayTarget
from integrations.triggers import TriggerDispatcher, TriggerEvent
from models.user import UserModel
from models.user_services import UserServicesModel
from schemas.lua import LuaRequest
from schemas.payments import Payment

router = APIRouter(prefix="/api/v1/callback/payment", tags=["callback"])


async def _build_request(request: Request) -> LuaRequest:
    """Собрать :class:`LuaRequest` из вебхука: метод, ip, заголовки, query, тело.

    Тело парсится как JSON, иначе как форма. Скрипт провайдера сам проверяет
    подпись по заголовкам/телу.
    """
    body: dict = {}
    try:
        parsed = await request.json()
        if isinstance(parsed, dict):
            body = parsed
    except Exception:  # noqa: BLE001 — не JSON, пробуем форму
        try:
            form = await request.form()
            body = {k: v for k, v in form.items()}
        except Exception:  # noqa: BLE001 — пустое/нечитаемое тело
            body = {}
    return LuaRequest.build(
        method=request.method,
        ip=request.client.host if request.client else None,
        headers={k.lower(): v for k, v in request.headers.items()},
        query=dict(request.query_params),
        body=body,
    )


async def _notify(svc: PayMngr, triggers: TriggerDispatcher, payment) -> None:
    """Best-effort триггеры по итогам колбэка (оплата/выдача услуги)."""
    if payment.status != PayStatus.PAID:
        return
    acc = await svc.s.get(UserModel, payment.account_id)
    email = acc.email if acc else None
    base = {
        "user": {
            "id": getattr(acc, "id", None),
            "login": getattr(acc, "login", None),
            "email": email,
        },
        "payment": {
            "id": payment.id,
            "amount": str(payment.amount),
            "currency": payment.currency,
            "target": payment.target,
        },
    }
    await triggers.fire(TriggerEvent.PAYMENT_PAID, base)

    if payment.target == PayTarget.SERVICE and payment.user_svc_id:
        usvc = await svc.s.get(UserServicesModel, payment.user_svc_id)
        if usvc is not None:
            ctx = {
                **base,
                "service": {
                    "id": usvc.service_id,
                    "status": usvc.status,
                    "public_data": usvc.public_data or {},
                },
            }
            await triggers.fire(TriggerEvent.SERVICE_DELIVERED, ctx)


@router.post(
    "/{provider}",
    response_model=Payment,
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
    triggers: TriggerDispatcher = Depends(get_dispatcher),
) -> Payment:
    data = await _build_request(request)
    payment = await svc.callback(provider, data)
    await svc.s.commit()
    await _notify(svc, triggers, payment)
    return payment


__all__ = ["router"]
