"""Единый сборщик контекста Lua и исполнитель скриптов «под нужным тегом».

Один целостный слой для трёх классов скриптов (service/payment/trigger): строит
контекст из схем :mod:`schemas.lua` и отправляет его в LuaWorker через шину.
См. UPDATE_PLAN.md, «Для работы с LUA создать 1 целостный скрипт в services».
"""

from __future__ import annotations

from enums import ScriptKind
from schemas.lua import (
    LuaAuthProvider,
    LuaMeta,
    LuaPayment,
    LuaProvider,
    LuaRequest,
    LuaService,
    LuaTrigger,
    LuaUser,
)
from utils.luabus import LuaBus


def _lua_meta(script) -> dict | None:  # noqa: ANN001 — SystemScriptsModel | None
    """Собрать объект ``ctx.lua`` из модели скрипта (или ``None``)."""
    if script is None:
        return None
    return LuaMeta.from_model(script).model_dump(mode="json")


def build_service_ctx(
    action: str,
    acc,  # noqa: ANN001 — UserModel
    usvc,  # noqa: ANN001 — UserServicesModel
    service,  # noqa: ANN001 — ServiceModel
    payment=None,  # noqa: ANN001 — UserPaymentsModel | None
    script=None,  # noqa: ANN001 — SystemScriptsModel | None
) -> dict:
    """Контекст скрипта услуги.

    :arg action: действие ЖЦ (create/renew/stop/delete/freeze).
    :arg acc: аккаунт-владелец.
    :arg usvc: выданная услуга (данные попадают в ``user.service``).
    :arg service: эталонная услуга.
    :arg payment: платёж, по которому выдана услуга (опционально).
    :arg script: модель шаблона — метаданные и настройки в ``lua.*`` (опционально).
    :return: словарь контекста для Lua.
    """
    ctx = {
        "action": action,
        "lua": _lua_meta(script),
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
    script=None,  # noqa: ANN001 — SystemScriptsModel | None
) -> dict:
    """Контекст платёжного скрипта.

    :arg action: create/callback/check/refund.
    :arg acc: аккаунт-плательщик.
    :arg payment: платёж.
    :arg provider: провайдер (источник секретов через ``payment.provider``).
    :arg secrets: расшифрованные секреты провайдера.
    :arg request: данные входящего запроса (только для callback).
    :arg return_url: ссылка возврата (для create).
    :arg script: модель шаблона — метаданные и настройки в ``lua.*`` (опционально).
        Секреты провайдера остаются в ``payment.provider_data`` и не конфликтуют
        с ``lua.settings``.
    :return: словарь контекста для Lua.
    """
    prov = LuaProvider.from_model(provider, secrets)
    ctx = {
        "action": action,
        "lua": _lua_meta(script),
        "user": LuaUser.from_model(acc).model_dump(mode="json"),
        "payment": LuaPayment.from_model(
            payment, provider=prov, return_url=return_url
        ).model_dump(mode="json"),
    }
    if request is not None:
        ctx["request"] = request.model_dump(mode="json")
    return ctx


def build_auth_ctx(
    action: str,
    provider,  # noqa: ANN001 — OAuthProvidersModel
    secrets: dict,
    *,
    redirect_uri: str,
    state: str | None = None,
    code: str | None = None,
    nonce: str | None = None,
    expected_nonce: str | None = None,
    request: LuaRequest | None = None,
    script=None,  # noqa: ANN001 — SystemScriptsModel | None
) -> dict:
    """Контекст OAuth-скрипта (action-driven, как у платежей).

    :arg action: start (построить authorize_url) | callback (обмен кода на профиль).
    :arg provider: ORM-провайдер (источник scopes/extra).
    :arg secrets: расшифрованные секреты провайдера (client_id/secret, endpoints).
    :arg redirect_uri: callback-URL нашей системы для этого провайдера.
    :arg state: антифрод-метка (для start — что положить в url; для callback — сверка).
    :arg code: код авторизации от провайдера (только для callback).
    :arg nonce: nonce, сгенерированный платформой (для start — что передать
        провайдеру в authorize-запросе, если скрипт поддерживает OIDC nonce).
    :arg expected_nonce: тот же nonce, восстановленный платформой из Valkey по
        ``state`` (для callback) — скрипт сам решает, сверять ли его с claim
        ``nonce`` из ``id_token`` (не все провайдеры используют OIDC).
    :arg request: данные входящего запроса callback (опционально).
    :arg script: модель шаблона — метаданные и настройки в ``lua.*`` (опционально).
        Секреты провайдера лежат в ``provider.secrets`` и не конфликтуют с
        ``lua.settings``.
    :return: словарь контекста для Lua.
    """
    ctx = {
        "action": action,
        "lua": _lua_meta(script),
        "provider": LuaAuthProvider.from_model(provider, secrets).model_dump(
            mode="json"
        ),
        "redirect_uri": redirect_uri,
        "state": state,
        "code": code,
        "nonce": nonce,
        "expected_nonce": expected_nonce,
    }
    if request is not None:
        ctx["request"] = request.model_dump(mode="json")
    return ctx


def build_trigger_ctx(
    event: str, config: dict, data: dict, script=None
) -> dict:  # noqa: ANN001
    """Контекст триггерного скрипта.

    :arg event: событие-условие.
    :arg config: полная конфигурация действия триггера.
    :arg data: унифицированные данные события (кто/что запустил).
    :arg script: модель шаблона — метаданные и настройки в ``lua.*`` (опционально).
    :return: словарь контекста для Lua.
    """
    ctx = LuaTrigger(event=event, config=config or {}, data=data or {}).model_dump(
        mode="json"
    )
    ctx["lua"] = _lua_meta(script)
    return ctx


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
        self, script, action, acc, usvc, service, payment=None
    ) -> dict:  # noqa: ANN001
        """Собрать контекст услуги и исполнить скрипт.

        :arg script: модель скрипта (``SystemScriptsModel``) — источник имени файла
            и данных ``lua.*``/``lua.settings.*``.
        """
        ctx = build_service_ctx(action, acc, usvc, service, payment, script)
        return await self.run(script.filename, ScriptKind.SERVICE, ctx)

    async def run_payment(
        self,
        script,  # noqa: ANN001 — SystemScriptsModel
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
            action, acc, payment, provider, secrets, request, return_url, script
        )
        return await self.run(script.filename, ScriptKind.PAYMENT, ctx)

    async def run_trigger(
        self, script, event: str, config: dict, data: dict
    ) -> dict:  # noqa: ANN001
        """Собрать контекст триггера и исполнить скрипт."""
        ctx = build_trigger_ctx(event, config, data, script)
        return await self.run(script.filename, ScriptKind.TRIGGER, ctx)

    async def run_auth(
        self,
        script,  # noqa: ANN001 — SystemScriptsModel
        action,  # noqa: ANN001
        provider,  # noqa: ANN001 — OAuthProvidersModel
        secrets,
        *,
        redirect_uri: str,
        state: str | None = None,
        code: str | None = None,
        nonce: str | None = None,
        expected_nonce: str | None = None,
        request=None,
    ) -> dict:
        """Собрать контекст OAuth и исполнить скрипт провайдера."""
        ctx = build_auth_ctx(
            action,
            provider,
            secrets,
            redirect_uri=redirect_uri,
            state=state,
            code=code,
            nonce=nonce,
            expected_nonce=expected_nonce,
            request=request,
            script=script,
        )
        return await self.run(script.filename, ScriptKind.AUTH, ctx)


__all__ = [
    "LuaRunner",
    "build_service_ctx",
    "build_payment_ctx",
    "build_auth_ctx",
    "build_trigger_ctx",
]
