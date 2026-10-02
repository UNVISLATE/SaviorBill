"""Юнит-тесты ключа rate-limit дependency (AUDIT.md §2.1).

Раньше лимитер ключевался по сырому (невалидированному) заголовку
``Authorization: Bearer ...`` — атакующий, подставляя новый случайный Bearer
на каждый запрос, получал новый бакет и обходил лимит полностью. Публичные
роуты теперь ключуются только по IP (Bearer не участвует вовсе), приватные —
по ``user_id`` из уже провалидированного здесь же access-токена.
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Response
from valkey.exceptions import ConnectionError as ValkeyConnectionError

from dependencies.auth import get_current_acc
from dependencies.ratelimit import (
    LimitKind,
    _authenticated_ident,
    _client_ip,
    _enforce,
    rate_limit,
)

pytestmark = pytest.mark.unit


def _fake_request(ip: str) -> SimpleNamespace:
    return SimpleNamespace(client=SimpleNamespace(host=ip))


def test_client_ip_ignores_any_headers():
    """``_client_ip`` не смотрит на Authorization вовсе — только на peer IP."""
    req = _fake_request("203.0.113.9")
    assert _client_ip(req) == "ip:203.0.113.9"


def test_client_ip_unknown_without_peer():
    req = SimpleNamespace(client=None)
    assert _client_ip(req) == "ip:unknown"


def test_authenticated_ident_uses_account_id_not_raw_token():
    acc = SimpleNamespace(id=42)
    assert _authenticated_ident(acc) == "user:42"


def test_public_dependency_has_no_bearer_parsing():
    """Публичный ``rate_limit()`` (require_auth=False, дефолт) не принимает
    учётные данные Bearer вообще — ключ детерминирован только IP, подделать
    его заголовком нельзя."""
    dep = rate_limit("some.public.scope")
    params = inspect.signature(dep).parameters
    assert "acc" not in params
    assert not any(
        "credentials" in name.lower() or "cred" == name for name in params
    )


def test_authenticated_dependency_requires_validated_account():
    """``require_auth=True`` форсирует ``get_current_acc`` (полная проверка
    подписи/exp/typ токена) как часть самого лимитера, а не полагается на
    порядок выполнения соседних FastAPI-зависимостей."""
    dep = rate_limit("some.private.scope", require_auth=True)
    params = inspect.signature(dep).parameters
    assert "acc" in params
    assert params["acc"].default.dependency is get_current_acc


def test_scope_and_kind_metadata_preserved_for_openapi():
    dep = rate_limit("scope.x", LimitKind.SENSITIVE, require_auth=True)
    assert dep._rate_limit_scope == "scope.x"
    assert dep._rate_limit_kind == LimitKind.SENSITIVE


def test_critical_kind_is_available_for_side_effecting_endpoints():
    assert LimitKind.CRITICAL.value == "critical"


@pytest.mark.asyncio
async def test_critical_rate_limit_fails_closed_on_valkey(monkeypatch):
    async def unavailable(*_args, **_kwargs):
        raise ValkeyConnectionError("down")

    monkeypatch.setattr("dependencies.ratelimit._resolve_rule", unavailable)
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                settings=SimpleNamespace(RATE_LIMIT_ENABLED=True),
                valkey=object(),
            )
        )
    )
    with pytest.raises(HTTPException) as exc:
        await _enforce(
            request,
            Response(),
            object(),
            "ip:test",
            "payment.callback",
            LimitKind.CRITICAL,
        )
    assert exc.value.status_code == 503
