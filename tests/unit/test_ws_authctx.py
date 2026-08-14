"""Юнит-тесты защит WS-хендшейка (AUDIT.md §3.1-§3.4): лимит pre-auth
соединений на IP, лимит размера фрейма, обработка бинарных фреймов,
периодическая перепроверка токена/прав уже открытого соединения.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import WebSocketDisconnect
from starlette import status as ws_status

from apiws.authctx import (
    REAUTH_INTERVAL_SEC,
    _acquire_preauth_slot,
    _release_preauth_slot,
    safe_receive_text,
    watch_session,
)

pytestmark = pytest.mark.unit


class _FakeValkey:
    def __init__(self) -> None:
        self._vals: dict[str, int] = {}
        self._ttl: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self._vals[key] = self._vals.get(key, 0) + 1
        return self._vals[key]

    async def decr(self, key: str) -> int:
        self._vals[key] = self._vals.get(key, 0) - 1
        return self._vals[key]

    async def expire(self, key: str, ttl: int) -> None:
        self._ttl[key] = ttl


class _FakeWS:
    def __init__(self, *, ip: str = "1.2.3.4", max_per_ip: int = 3, max_frame_bytes: int = 1024):
        self.client = SimpleNamespace(host=ip)
        self.app = SimpleNamespace(
            state=SimpleNamespace(
                valkey=_FakeValkey(),
                settings=SimpleNamespace(
                    WS_PREAUTH_MAX_PER_IP=max_per_ip,
                    WS_MAX_FRAME_BYTES=max_frame_bytes,
                    WS_HANDSHAKE_TIMEOUT_SEC=10,
                ),
            )
        )
        self.closed_code: int | None = None
        self._messages: list[dict] = []

    async def close(self, code: int) -> None:
        self.closed_code = code

    def push_message(self, message: dict) -> None:
        self._messages.append(message)

    async def receive(self) -> dict:
        if not self._messages:
            # Имитируем "никогда не придёт" — вызывающая сторона использует
            # asyncio.wait_for с таймаутом.
            await asyncio.Event().wait()
        return self._messages.pop(0)


# ─────────────────────────────────────────────────────────────────────────────
# Лимит pre-auth соединений на IP (§3.1)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_preauth_slot_allows_up_to_limit():
    ws = _FakeWS(max_per_ip=2)
    assert await _acquire_preauth_slot(ws) is True
    assert await _acquire_preauth_slot(ws) is True


@pytest.mark.asyncio
async def test_preauth_slot_rejects_over_limit():
    ws = _FakeWS(max_per_ip=2)
    assert await _acquire_preauth_slot(ws) is True
    assert await _acquire_preauth_slot(ws) is True
    assert await _acquire_preauth_slot(ws) is False


@pytest.mark.asyncio
async def test_preauth_slot_released_frees_capacity():
    ws = _FakeWS(max_per_ip=1)
    assert await _acquire_preauth_slot(ws) is True
    assert await _acquire_preauth_slot(ws) is False
    await _release_preauth_slot(ws)
    assert await _acquire_preauth_slot(ws) is True


@pytest.mark.asyncio
async def test_preauth_slot_independent_per_ip():
    ws_a = _FakeWS(ip="1.1.1.1", max_per_ip=1)
    ws_b = _FakeWS(ip="2.2.2.2", max_per_ip=1)
    ws_b.app.state.valkey = ws_a.app.state.valkey  # общий Valkey, разные IP-ключи
    assert await _acquire_preauth_slot(ws_a) is True
    assert await _acquire_preauth_slot(ws_b) is True


# ─────────────────────────────────────────────────────────────────────────────
# safe_receive_text: лимит размера фрейма (§3.2) и бинарные фреймы (§3.3)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_safe_receive_text_returns_text():
    ws = _FakeWS()
    ws.push_message({"type": "websocket.receive", "text": '{"token":"x"}'})
    assert await safe_receive_text(ws) == '{"token":"x"}'
    assert ws.closed_code is None


@pytest.mark.asyncio
async def test_safe_receive_text_rejects_binary_frame():
    """Раньше receive_text() падал KeyError на бинарном фрейме — необработанное
    исключение вне списка перехватываемых (AUDIT.md §3.3)."""
    ws = _FakeWS()
    ws.push_message({"type": "websocket.receive", "bytes": b"\x00\x01"})
    result = await safe_receive_text(ws)
    assert result is None
    assert ws.closed_code == ws_status.WS_1003_UNSUPPORTED_DATA


@pytest.mark.asyncio
async def test_safe_receive_text_rejects_oversized_frame():
    ws = _FakeWS(max_frame_bytes=8)
    ws.push_message({"type": "websocket.receive", "text": "x" * 100})
    result = await safe_receive_text(ws)
    assert result is None
    assert ws.closed_code == ws_status.WS_1009_MESSAGE_TOO_BIG


@pytest.mark.asyncio
async def test_safe_receive_text_timeout_closes_4401():
    ws = _FakeWS()  # очередь сообщений пуста -> receive() зависает навсегда
    result = await safe_receive_text(ws, timeout=0.05)
    assert result is None
    assert ws.closed_code == 4401


@pytest.mark.asyncio
async def test_safe_receive_text_disconnect_message_returns_none():
    ws = _FakeWS()
    ws.push_message({"type": "websocket.disconnect"})
    result = await safe_receive_text(ws)
    assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# watch_session: периодическая перепроверка токена/прав (§3.4)
# ─────────────────────────────────────────────────────────────────────────────


class _FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeUserMngr:
    def __init__(self, acc):
        self._acc = acc

    async def by_id(self, acc_id: int):
        return self._acc


def _watchdog_ws(acc) -> SimpleNamespace:
    closed = {"code": None}

    async def close(code: int) -> None:
        closed["code"] = code

    ws = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(db_sessionmaker=lambda: _FakeSession())
        ),
        close=close,
        _closed=closed,
    )
    return ws


@pytest.mark.asyncio
async def test_watch_session_closes_on_expired_token(monkeypatch):
    import apiws.authctx as authctx_mod

    monkeypatch.setattr(authctx_mod, "REAUTH_INTERVAL_SEC", 0.01)
    acc = SimpleNamespace(id=1, role=SimpleNamespace(perms={"x": True}))
    monkeypatch.setattr(
        authctx_mod, "UserMngr", lambda session: _FakeUserMngr(acc)
    )
    ws = _watchdog_ws(acc)
    past_exp = 0  # уже истёк
    await asyncio.wait_for(watch_session(ws, acc.id, past_exp, "x"), timeout=2)
    assert ws._closed["code"] == 4401


@pytest.mark.asyncio
async def test_watch_session_closes_when_perm_revoked(monkeypatch):
    import apiws.authctx as authctx_mod

    monkeypatch.setattr(authctx_mod, "REAUTH_INTERVAL_SEC", 0.01)
    acc = SimpleNamespace(id=1, role=SimpleNamespace(perms={}))  # право отозвано
    monkeypatch.setattr(
        authctx_mod, "UserMngr", lambda session: _FakeUserMngr(acc)
    )
    ws = _watchdog_ws(acc)
    future_exp = 9_999_999_999
    await asyncio.wait_for(watch_session(ws, acc.id, future_exp, "needed.perm"), timeout=2)
    assert ws._closed["code"] == 4401


@pytest.mark.asyncio
async def test_watch_session_keeps_alive_while_valid(monkeypatch):
    import apiws.authctx as authctx_mod

    monkeypatch.setattr(authctx_mod, "REAUTH_INTERVAL_SEC", 0.01)
    acc = SimpleNamespace(id=1, role=SimpleNamespace(perms={"x": True}))
    monkeypatch.setattr(
        authctx_mod, "UserMngr", lambda session: _FakeUserMngr(acc)
    )
    ws = _watchdog_ws(acc)
    future_exp = 9_999_999_999
    task = asyncio.create_task(watch_session(ws, acc.id, future_exp, "x"))
    await asyncio.sleep(0.05)
    assert ws._closed["code"] is None
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
