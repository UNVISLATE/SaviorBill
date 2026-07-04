"""Юнит-тесты utils/luabus — шина Python ↔ LuaWorker."""

from __future__ import annotations

import json
import uuid

import pytest

from utils.luabus import LuaBus, LuaError

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

    async def xadd(self, stream: str, fields: dict) -> str:
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

    async def capturing_xadd(stream: str, fields: dict) -> str:
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

    async def capturing_xadd(stream: str, fields: dict) -> str:
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

    async def capturing_xadd(stream: str, fields: dict) -> str:
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

    async def capturing_xadd(stream: str, fields: dict) -> str:
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
