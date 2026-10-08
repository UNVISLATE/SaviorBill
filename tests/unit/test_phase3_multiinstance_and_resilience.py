"""Юнит-тесты для Фазы 3: Мульти-инстанс и устойчивость инфраструктуры.

Проверяет:
1. Распределённые блокировки Valkey в BillingLoop и MediaJobEvents.
2. Сохранение и чтение тела email-шаблонов напрямую из базы данных (PostgreSQL).
3. Анти-петлю глубины вызова триггеров (_TRIGGER_MAX_DEPTH = 5).
4. Отзыв сессий с сохранением текущей сессии (except_session_id).
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from lifecycle.triggers import BaseAction, TriggerDispatcher
from models.email_templates import EmailMngr, EmailModel
from services.billing_loop import BillingLoop
from services.media_job_events import MediaJobEvents
from services.auth import TokenSvc


class _FakeValkey:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}
        self.hashes: dict[str, dict[str, str]] = {}
        self.sets_calls: list[tuple[str, str]] = []

    async def set(
        self, key: str, value: str, *, nx: bool = False, ex: int | None = None
    ) -> bool:
        self.sets_calls.append((key, value))
        if nx and key in self.data:
            return False
        self.data[key] = value
        return True

    async def exists(self, *keys: str) -> int:
        return sum(1 for k in keys if k in self.data or k in self.hashes)

    async def delete(self, *keys: str) -> int:
        n = 0
        for k in keys:
            if k in self.data:
                del self.data[k]
                n += 1
            if k in self.hashes:
                del self.hashes[k]
                n += 1
        return n

    async def scan_iter(self, match: str = "*"):
        prefix = match.rstrip("*")
        for k in list(self.hashes.keys()):
            if k.startswith(prefix):
                yield k

    async def hgetall(self, key: str) -> dict[str, str]:
        return self.hashes.get(key, {})


class _RecursiveAction(BaseAction):
    def __init__(self, dispatcher: TriggerDispatcher) -> None:
        self.dispatcher = dispatcher
        self.call_count = 0

    async def run(self, event: str, ctx: dict, config: dict) -> bool:
        self.call_count += 1
        await self.dispatcher.fire("chain_event", ctx)
        return True


class _FakeTrigMngr:
    def __init__(self, trigs: list) -> None:
        self._trigs = trigs

    async def by_event(self, event: str) -> list:
        return [t for t in self._trigs if t.event == event]


# --- 1. Тесты блокировок BillingLoop ---

@pytest.mark.asyncio
async def test_billing_loop_seed_lock_prevents_duplicate_seeding() -> None:
    vk = _FakeValkey()
    await vk.set("lock:billing:seed", "1", nx=True, ex=5)

    loop = BillingLoop.__new__(BillingLoop)
    loop.cfg = SimpleNamespace(BILLING_LOOP_ENABLED=True)
    loop.vk = vk
    loop.seed_on_start = AsyncMock()

    with patch("asyncio.create_task") as mock_task:
        mock_task.return_value = None
        await loop.start()

    loop.seed_on_start.assert_not_called()


@pytest.mark.asyncio
async def test_media_job_events_sweep_stale_lock() -> None:
    vk = _FakeValkey()
    await vk.set("lock:billing:sweep_stale", "1", nx=True, ex=30)

    events = MediaJobEvents.__new__(MediaJobEvents)
    events.vk = vk
    events.cfg = SimpleNamespace(MEDIA_JOB_STALE_AFTER_SEC=300)
    events._last_sweep = 0.0
    events.sm = AsyncMock()

    # При наличии активного лока другого инстанса _maybe_sweep не трогает БД
    await events._maybe_sweep()
    events.sm.assert_not_called()


# --- 2. Тесты email-шаблонов в БД ---

@pytest.mark.asyncio
async def test_email_mngr_reads_from_body_column_without_filesystem() -> None:
    mngr = EmailMngr(session=None, templates_dir="/nonexistent/directory")
    row = EmailModel(
        slug="test_slug",
        subject="Тема",
        filename="dummy.j2",
        body="<h1>Привет из БД!</h1>",
        is_html=True,
    )
    body = await mngr.read_body(row)
    assert body == "<h1>Привет из БД!</h1>"


# --- 3. Тесты анти-петли глубины триггеров ---

@pytest.mark.asyncio
async def test_trigger_depth_limit_prevents_infinite_recursion() -> None:
    trigs = [
        SimpleNamespace(id=1, event="chain_event", action="rec", cond={}, config={})
    ]
    dispatcher = TriggerDispatcher(
        triggers=_FakeTrigMngr(trigs),
        actions={},
        settings=None,
    )
    recursive_action = _RecursiveAction(dispatcher)
    dispatcher.actions["rec"] = recursive_action

    await dispatcher.fire("chain_event", {})

    assert recursive_action.call_count == 5, f"Expected 5 calls, got {recursive_action.call_count}"


# --- 4. Тесты отзыва сессий с сохранением текущей ---

@pytest.mark.asyncio
async def test_revoke_all_sessions_keeps_current_session(rsa_keypair) -> None:
    priv, pub = rsa_keypair
    cfg = SimpleNamespace(
        JWT_PRIVATE_KEY=priv,
        JWT_PUBLIC_KEY=pub,
        JWT_ALG="RS256",
        JWT_ISS="test",
        JWT_KID="k1",
        ACCESS_TOKEN_TTL=300,
        REFRESH_TOKEN_TTL=3600,
        AUTH_SESSION_HASH_KEY="secret-session-hash-key",
        jwt_public_keys=lambda: {"k1": pub},
    )
    vk = _FakeValkey()
    vk.hashes["session:7:keep_jti"] = {"exp": "99999999999"}
    vk.hashes["session:7:other1"] = {"exp": "99999999999"}
    vk.hashes["session:7:other2"] = {"exp": "99999999999"}

    svc = TokenSvc(cfg, vk, session=None)
    current_sid = svc._session_digest("keep_jti")

    revoked = await svc.revoke_all_sessions(7, except_session_id=current_sid)
    assert revoked == 2

    assert "session:7:keep_jti" in vk.hashes
    assert not await svc.is_revoked("keep_jti")

    assert "session:7:other1" not in vk.hashes
    assert "session:7:other2" not in vk.hashes


# --- 5. Тесты двухуровневого Rate Limiter ---

@pytest.mark.asyncio
async def test_dual_level_rate_limiter_inspect() -> None:
    import inspect
    from dependencies.ratelimit import rate_limit, LimitKind

    dep = rate_limit("test.dual", LimitKind.DEFAULT, require_auth=True)
    sig = inspect.signature(dep)
    assert "acc" in sig.parameters
    assert "request" in sig.parameters
    assert "response" in sig.parameters
