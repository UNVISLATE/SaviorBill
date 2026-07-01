"""Единый сборщик контекста Lua и исполнитель скриптов «под нужным тегом».

Один целостный слой для трёх классов скриптов (service/payment/trigger): строит
контекст из схем :mod:`schemas.lua` и отправляет его в LuaWorker через шину.
См. UPDATE_PLAN.md, «Для работы с LUA создать 1 целостный скрипт в services».
"""

from __future__ import annotations

from enums import ScriptKind
from schemas.lua import (
    LuaPayment,
    LuaProvider,
    LuaRequest,
    LuaService,
    LuaTrigger,
    LuaUser,
)
from utils.luabus import LuaBus


def build_service_ctx(
    action: str,
    acc,  # noqa: ANN001 — UserModel
    usvc,  # noqa: ANN001 — UserServicesModel
    service,  # noqa: ANN001 — ServiceModel
    payment=None,  # noqa: ANN001 — UserPaymentsModel | None
) -> dict:
    """Контекст скрипта услуги.

    :arg action: действие ЖЦ (create/renew/stop/delete/freeze).
    :arg acc: аккаунт-владелец.
    :arg usvc: выданная услуга (данные попадают в ``user.service``).
    :arg service: эталонная услуга.
    :arg payment: платёж, по которому выдана услуга (опционально).
    :return: словарь контекста для Lua.
    """
    ctx = {
        "action": action,
        "user": LuaUser.from_model(acc, usvc).model_dump(mode="json"),
        "service": LuaService.from_model(service).model_dump(mode="json"),
        "payment": (
            LuaPayment.from_model(payment).model_dump(mode="json")
            if payment is not None
            else None
        ),
    }
    return ctx


def build_payment_ctx(
    action: str,
    acc,  # noqa: ANN001 — UserModel
    payment,  # noqa: ANN001 — UserPaymentsModel
    provider,  # noqa: ANN001 — PaymentProvidersModel
    secrets: dict,
    request: LuaRequest | None = None,
    return_url: str | None = None,
) -> dict:
    """Контекст платёжного скрипта.

    :arg action: create/callback/check/refund.
    :arg acc: аккаунт-плательщик.
    :arg payment: платёж.
    :arg provider: провайдер (источник секретов через ``payment.provider``).
    :arg secrets: расшифрованные секреты провайдера.
    :arg request: данные входящего запроса (только для callback).
    :arg return_url: ссылка возврата (для create).
    :return: словарь контекста для Lua.
    """
    prov = LuaProvider.from_model(provider, secrets)
    ctx = {
        "action": action,
        "user": LuaUser.from_model(acc).model_dump(mode="json"),
        "payment": LuaPayment.from_model(
            payment, provider=prov, return_url=return_url
        ).model_dump(mode="json"),
    }
    if request is not None:
        ctx["request"] = request.model_dump(mode="json")
    return ctx


def build_trigger_ctx(event: str, config: dict, data: dict) -> dict:
    """Контекст триггерного скрипта.

    :arg event: событие-условие.
    :arg config: полная конфигурация действия триггера.
    :arg data: унифицированные данные события (кто/что запустил).
    :return: словарь контекста для Lua.
    """
    return LuaTrigger(event=event, config=config or {}, data=data or {}).model_dump(
        mode="json"
    )


class LuaRunner:
    """Исполнитель Lua-скриптов: строит контекст и вызывает LuaWorker под тегом."""

    def __init__(self, bus: LuaBus) -> None:
        self.bus = bus

    async def run(self, script_filename: str, kind: str, ctx: dict) -> dict:
        """Отправить скрипт с контекстом в LuaWorker.

        :arg script_filename: имя файла скрипта относительно LUA_SCRIPTS_DIR.
        :arg kind: класс скрипта (тег), см. :class:`enums.ScriptKind`.
        :arg ctx: собранный контекст.
        :return: результат исполнения ({public, private, state, expires_at, …}).
        """
        return await self.bus.call(
            "run_script",
            {"script": script_filename, "kind": kind, "ctx": ctx},
        )

    async def run_service(
        self, script_filename: str, action, acc, usvc, service, payment=None
    ) -> dict:  # noqa: ANN001
        """Собрать контекст услуги и исполнить скрипт."""
        ctx = build_service_ctx(action, acc, usvc, service, payment)
        return await self.run(script_filename, ScriptKind.SERVICE, ctx)

    async def run_payment(
        self,
        script_filename: str,
        action,  # noqa: ANN001
        acc,
        payment,
        provider,
        secrets,
        request=None,
        return_url=None,
    ) -> dict:
        """Собрать контекст платежа и исполнить скрипт."""
        ctx = build_payment_ctx(
            action, acc, payment, provider, secrets, request, return_url
        )
        return await self.run(script_filename, ScriptKind.PAYMENT, ctx)

    async def run_trigger(
        self, script_filename: str, event: str, config: dict, data: dict
    ) -> dict:
        """Собрать контекст триггера и исполнить скрипт."""
        ctx = build_trigger_ctx(event, config, data)
        return await self.run(script_filename, ScriptKind.TRIGGER, ctx)


__all__ = [
    "LuaRunner",
    "build_service_ctx",
    "build_payment_ctx",
    "build_trigger_ctx",
]
