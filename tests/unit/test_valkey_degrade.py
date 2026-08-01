"""Мягкая деградация при недоступности Valkey (см. AUDIT.md §2.3).

Rate-limit, анти-брутфорс и трекинг сессий вспомогательны: их отказ не должен
превращаться в отказ в обслуживании всей платформы.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from valkey.exceptions import ConnectionError as ValkeyConnectionError

from dependencies.login_guard import LoginGuard
from services.auth import TokenSvc

pytestmark = pytest.mark.unit


class _DeadValkey:
    """Любая операция падает так, как падал бы недоступный Valkey."""

    def __getattr__(self, _name):
        async def _boom(*_a, **_kw):
            raise ValkeyConnectionError("connection refused")

        return _boom


class _Settings:
    async def get_int(self, _key, default=None):
        return default


@pytest.mark.asyncio
async def test_login_guard_check_does_not_block_when_valkey_is_down():
    guard = LoginGuard(_DeadValkey(), _Settings())
    await guard.check("alice", "1.2.3.4")


@pytest.mark.asyncio
async def test_login_guard_record_and_clear_survive_valkey_outage():
    guard = LoginGuard(_DeadValkey(), _Settings())
    await guard.record_fail("alice", "1.2.3.4")
    await guard.clear("alice")


def _cfg():
    return SimpleNamespace(
        JWT_SECRET="x" * 32,
        JWT_ALG="HS256",
        JWT_ISS="saviorbill",
        ACCESS_TOKEN_TTL=900,
        REFRESH_TOKEN_TTL=86400,
    )


@pytest.mark.asyncio
async def test_issue_tracked_still_returns_tokens_when_valkey_is_down():
    acc = SimpleNamespace(id=1, login="alice", role=None, is_active=True)
    svc = TokenSvc(_cfg(), _DeadValkey())
    pair = await svc.issue_tracked(acc, ip="1.2.3.4", user_agent="ua")
    assert pair.access_token and pair.refresh_token
