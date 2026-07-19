"""Юнит-тесты utils/luabus — шина Python ↔ LuaWorker."""

from __future__ import annotations

import json
import uuid

import pytest

from lua.bus import LuaBus, LuaError, _MAX_DETAIL_LEN, _safe_detail

pytestmark = pytest.mark.unit


class FakeValkey:
    """Минимальный фейк Valkey Streams для тестирования LuaBus."""

    def __init__(self, responses: list[dict] | None = None) -> None:
        """
        :arg responses: список ответов воркера, которые будут возвращены по очереди.
            Каждый элемент — dict с ключами 'ok', 'data' и опциональным 'cid'.
        """
        self._responses = responses or []
        self._stream_entries: dict[str, list[tuple[str, dict]]] = {}
        self._counter = 0
        self.added_tasks: list[dict] = []
        self._raise_on_xinfo: Exception | None = None

    def _next_id(self) -> str:
        self._counter += 1
        return f"0-{self._counter}"

    async def xinfo_stream(self, stream: str) -> dict:
        if self._raise_on_xinfo:
            raise self._raise_on_xinfo
        entries = self._stream_entries.get(stream, [])
        last = entries[-1][0] if entries else "0-0"
        return {"last-generated-id": last}

    async def xadd(self, stream: str, fields: dict, **_kwargs) -> str:
        entry_id = self._next_id()
        self._stream_entries.setdefault(stream, []).append((entry_id, fields))
        if "kind" in fields:
            self.added_tasks.append(dict(fields))
        return entry_id

    async def xread(self, streams: dict, block: int = 0, count: int = 10):
        for stream, last_id in streams.items():
            entries = self._stream_entries.get(stream, [])
            new = [(eid, f) for eid, f in entries if eid > last_id]
            if new:
                return [(stream, new[:count])]
        return []


async def _inject_response(fake: FakeValkey, resp_stream: str, cid: str, response: dict) -> None:
    """Добавить ответ воркера в стрим ответов."""
    data = json.dumps(response.get("data"))
    ok = "1" if response.get("ok", True) else "0"
    await fake.xadd(resp_stream, {"cid": cid, "ok": ok, "data": data})


# ─────────────────────────────────────────────────────────────────────────────
# _last_id
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_last_id_empty_stream():
    """Пустой стрим → ResponseError → возвращает '0-0'."""
    from valkey.exceptions import ResponseError

    fake = FakeValkey()
    fake._raise_on_xinfo = ResponseError("no such key")
    bus = LuaBus(fake, "lua:tasks", "lua:results")
    assert await bus._last_id() == "0-0"


@pytest.mark.asyncio
async def test_last_id_with_entries():
    fake = FakeValkey()
    await fake.xadd("lua:results", {"x": "1"})
    bus = LuaBus(fake, "lua:tasks", "lua:results")
    last = await bus._last_id()
    assert last == "0-1"


# ─────────────────────────────────────────────────────────────────────────────
# submit
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_submit_returns_cid():
    fake = FakeValkey()
    bus = LuaBus(fake, "lua:tasks", "lua:results")
    cid = await bus.submit("eval", {"code": "return 1"})
    assert isinstance(cid, str)
    assert len(cid) == 32  # uuid hex


@pytest.mark.asyncio
async def test_submit_writes_to_task_stream():
    fake = FakeValkey()
    bus = LuaBus(fake, "lua:tasks", "lua:results")
    await bus.submit("eval", {"code": "return 42"})
    assert len(fake.added_tasks) == 1
    task = fake.added_tasks[0]
    assert task["kind"] == "eval"
    assert json.loads(task["payload"])["code"] == "return 42"


# ─────────────────────────────────────────────────────────────────────────────
# call
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_call_returns_dict_on_success():
    """Успешный ответ с dict data возвращается как есть."""
    fake = FakeValkey()
    bus = LuaBus(fake, "lua:tasks", "lua:results", default_timeout=5)

    # Перехватываем xadd задачи, чтобы знать cid.
    captured_cid: list[str] = []
    original_xadd = fake.xadd

    async def capturing_xadd(stream: str, fields: dict, **_kwargs) -> str:
        entry_id = await original_xadd(stream, fields)
        if "kind" in fields:
            captured_cid.append(fields["cid"])
            # Сразу кладём ответ в стрим результатов.
            resp_id = fake._next_id()
            fake._stream_entries.setdefault("lua:results", []).append(
                (resp_id, {"cid": fields["cid"], "ok": "1", "data": json.dumps({"result": 99})})
            )
        return entry_id

    fake.xadd = capturing_xadd

    result = await bus.call("eval", {"code": "return 99"})
    assert result == {"result": 99}


@pytest.mark.asyncio
async def test_call_wraps_scalar_result():
    """Скалярный ответ (не dict) оборачивается в {'result': value}."""
    fake = FakeValkey()
    bus = LuaBus(fake, "lua:tasks", "lua:results", default_timeout=5)

    original_xadd = fake.xadd

    async def capturing_xadd(stream: str, fields: dict, **_kwargs) -> str:
        entry_id = await original_xadd(stream, fields)
        if "kind" in fields:
            resp_id = fake._next_id()
            fake._stream_entries.setdefault("lua:results", []).append(
                (resp_id, {"cid": fields["cid"], "ok": "1", "data": json.dumps(42)})
            )
        return entry_id

    fake.xadd = capturing_xadd

    result = await bus.call("eval", {"code": "return 42"})
    assert result == {"result": 42}


@pytest.mark.asyncio
async def test_call_raises_lua_error_on_failure():
    """ok=0 → LuaError."""
    fake = FakeValkey()
    bus = LuaBus(fake, "lua:tasks", "lua:results", default_timeout=5)

    original_xadd = fake.xadd

    async def capturing_xadd(stream: str, fields: dict, **_kwargs) -> str:
        entry_id = await original_xadd(stream, fields)
        if "kind" in fields:
            resp_id = fake._next_id()
            fake._stream_entries.setdefault("lua:results", []).append(
                (resp_id, {"cid": fields["cid"], "ok": "0", "data": json.dumps("something failed")})
            )
        return entry_id

    fake.xadd = capturing_xadd

    with pytest.raises(LuaError, match="something failed"):
        await bus.call("eval", {})


@pytest.mark.asyncio
async def test_call_ignores_unrelated_entries():
    """Ответы с чужим cid должны игнорироваться; правильный cid найдётся."""
    fake = FakeValkey()
    bus = LuaBus(fake, "lua:tasks", "lua:results", default_timeout=5)

    original_xadd = fake.xadd

    async def capturing_xadd(stream: str, fields: dict, **_kwargs) -> str:
        entry_id = await original_xadd(stream, fields)
        if "kind" in fields:
            # Сначала добавляем чужой ответ.
            r1 = fake._next_id()
            fake._stream_entries.setdefault("lua:results", []).append(
                (r1, {"cid": "othercid", "ok": "1", "data": json.dumps({"x": 1})})
            )
            # Затем правильный.
            r2 = fake._next_id()
            fake._stream_entries.setdefault("lua:results", []).append(
                (r2, {"cid": fields["cid"], "ok": "1", "data": json.dumps({"result": 7})})
            )
        return entry_id

    fake.xadd = capturing_xadd

    result = await bus.call("eval", {})
    assert result == {"result": 7}


# ─────────────────────────────────────────────────────────────────────────────
# _safe_detail (AUDIT.md M3) — обрезка длинных сообщений об ошибке
# ─────────────────────────────────────────────────────────────────────────────

def test_safe_detail_keeps_short_text():
    assert _safe_detail("short error") == "short error"


def test_safe_detail_truncates_long_text():
    long_text = "x" * (_MAX_DETAIL_LEN + 50)
    result = _safe_detail(long_text)
    assert len(result) <= _MAX_DETAIL_LEN + len("…[truncated]")
    assert result.endswith("…[truncated]")


@pytest.mark.asyncio
async def test_call_error_detail_is_truncated_in_task_log():
    """Длинный текст ошибки от воркера обрезается до записи в task_log."""
    fake = FakeValkey()
    bus = LuaBus(fake, "lua:tasks", "lua:results", default_timeout=5)

    original_xadd = fake.xadd
    long_error = "leaked-secret-" * 50

    async def capturing_xadd(stream: str, fields: dict, **_kwargs) -> str:
        entry_id = await original_xadd(stream, fields)
        if "kind" in fields:
            resp_id = fake._next_id()
            fake._stream_entries.setdefault("lua:results", []).append(
                (resp_id, {"cid": fields["cid"], "ok": "0", "data": json.dumps(long_error)})
            )
        return entry_id

    fake.xadd = capturing_xadd

    with pytest.raises(LuaError) as exc_info:
        await bus.call("eval", {})
    assert len(str(exc_info.value)) < len(long_error)


# ─────────────────────────────────────────────────────────────────────────────
# H1 (AUDIT.md) — подпись сообщений шины (BUS_SIGNING_KEY)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_signed_bus_signs_outgoing_task():
    """При заданном signing_key исходящая задача содержит ts/sig."""
    fake = FakeValkey()
    bus = LuaBus(fake, "lua:tasks", "lua:results", signing_key="shared-secret")
    await bus.submit("eval", {"code": "return 1"})
    assert len(fake.added_tasks) == 1
    task = fake.added_tasks[0]
    assert "ts" in task and "sig" in task


@pytest.mark.asyncio
async def test_signed_bus_rejects_unsigned_response():
    """Ответ без подписи отклоняется — вызов уходит в таймаут."""
    fake = FakeValkey()
    bus = LuaBus(
        fake, "lua:tasks", "lua:results", default_timeout=1, signing_key="shared-secret"
    )

    original_xadd = fake.xadd

    async def capturing_xadd(stream: str, fields: dict, **_kwargs) -> str:
        entry_id = await original_xadd(stream, fields)
        if "kind" in fields:
            # Ответ воркера без ts/sig — как если бы кто-то подделал сообщение
            # или BUS_SIGNING_KEY воркера не совпадает.
            resp_id = fake._next_id()
            fake._stream_entries.setdefault("lua:results", []).append(
                (resp_id, {"cid": fields["cid"], "ok": "1", "data": json.dumps({"x": 1})})
            )
        return entry_id

    fake.xadd = capturing_xadd

    with pytest.raises(LuaError, match="таймаут"):
        await bus.call("eval", {})


@pytest.mark.asyncio
async def test_signed_bus_accepts_correctly_signed_response():
    """Ответ с верной подписью (и тем же ключом) принимается как обычно."""
    from security.sec.bus_sign import sign_fields

    fake = FakeValkey()
    bus = LuaBus(
        fake, "lua:tasks", "lua:results", default_timeout=5, signing_key="shared-secret"
    )

    original_xadd = fake.xadd

    async def capturing_xadd(stream: str, fields: dict, **_kwargs) -> str:
        entry_id = await original_xadd(stream, fields)
        if "kind" in fields:
            resp = sign_fields(
                "shared-secret",
                {"cid": fields["cid"], "ok": "1", "data": json.dumps({"result": 5})},
            )
            resp_id = fake._next_id()
            fake._stream_entries.setdefault("lua:results", []).append((resp_id, resp))
        return entry_id

    fake.xadd = capturing_xadd

    result = await bus.call("eval", {})
    assert result == {"result": 5}


# ─────────────────────────────────────────────────────────────────────────────
# call: ретраи (IMPLEMENTATION_PLAN §9)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_call_default_no_retry_raises_immediately():
    """max_retries=0 (по умолчанию) — старое поведение: одна попытка, без ретраев."""
    fake = FakeValkey()
    bus = LuaBus(fake, "lua:tasks", "lua:results", default_timeout=5)

    calls = 0

    async def failing_once(kind, payload, timeout):
        nonlocal calls
        calls += 1
        raise LuaError("timeout")

    bus._call_once = failing_once

    with pytest.raises(LuaError):
        await bus.call("eval", {})
    assert calls == 1


@pytest.mark.asyncio
async def test_call_retries_then_succeeds():
    """Ошибка на первых попытках, успех на последней — retry вернёт результат."""
    fake = FakeValkey()
    bus = LuaBus(
        fake, "lua:tasks", "lua:results", default_timeout=5, max_retries=2, retry_backoff=0
    )

    calls = 0

    async def flaky(kind, payload, timeout):
        nonlocal calls
        calls += 1
        if calls < 3:
            raise LuaError("временная ошибка воркера")
        return {"result": "ok"}

    bus._call_once = flaky

    result = await bus.call("eval", {})
    assert result == {"result": "ok"}
    assert calls == 3


@pytest.mark.asyncio
async def test_call_retries_exhausted_raises_last_error():
    """Все попытки исчерпаны — пробрасывается последняя ошибка."""
    fake = FakeValkey()
    bus = LuaBus(
        fake, "lua:tasks", "lua:results", default_timeout=5, max_retries=2, retry_backoff=0
    )

    calls = 0

    async def always_fails(kind, payload, timeout):
        nonlocal calls
        calls += 1
        raise LuaError(f"ошибка #{calls}")

    bus._call_once = always_fails

    with pytest.raises(LuaError, match="ошибка #3"):
        await bus.call("eval", {})
    # 1 исходная попытка + 2 ретрая = 3 вызова _call_once.
    assert calls == 3


@pytest.mark.asyncio
async def test_call_retry_sleeps_backoff_between_attempts(monkeypatch):
    """Между попытками действительно ждём retry_backoff секунд."""
    fake = FakeValkey()
    bus = LuaBus(
        fake, "lua:tasks", "lua:results", default_timeout=5, max_retries=1, retry_backoff=3
    )

    calls = 0

    async def flaky(kind, payload, timeout):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise LuaError("timeout")
        return {"result": "ok"}

    bus._call_once = flaky

    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr("lua.bus.asyncio.sleep", fake_sleep)

    result = await bus.call("eval", {})
    assert result == {"result": "ok"}
    assert sleeps == [3]
