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

from dependencies.auth import get_current_acc
from dependencies.ratelimit import _authenticated_ident, _client_ip, rate_limit

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
    from dependencies.ratelimit import LimitKind

    dep = rate_limit("scope.x", LimitKind.SENSITIVE, require_auth=True)
    assert dep._rate_limit_scope == "scope.x"
    assert dep._rate_limit_kind == LimitKind.SENSITIVE
