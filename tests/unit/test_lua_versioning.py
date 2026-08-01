"""Юнит-тесты Lua v2: дедуп версий по sha256, optimistic locking, activate/diff.

Реальную БД не поднимаем (см. read-only LUA_SCRIPTS_DIR в интеграционном
стенде — CRUD lua-скриптов через живой API там намеренно не тестируется,
tests/data/lua монтируется ``:ro``). Логика ``SystemScriptsMngr`` изолирована
от SQLAlchemy-сессии через минимальный фейк ниже.
"""

from __future__ import annotations

import hashlib
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from models.system_scripts import LuaScriptVersionModel, SystemScriptsMngr

pytestmark = pytest.mark.unit


class FakeSession:
    """Достаточно `session`-подобного поведения для patch()/activate_version()/diff().

    Не выполняет реальных SQL-запросов — методы ``by_id``/``get_version``
    подменяются на моках прямо в тестах, а ``add``/``flush`` этот фейк только
    фиксирует.
    """

    def __init__(self) -> None:
        self.added: list = []

    def add(self, obj) -> None:  # noqa: ANN001
        self.added.append(obj)

    async def flush(self) -> None:
        return None


def _script_row(**overrides) -> SimpleNamespace:
    code = "return { handle = function(ctx) end }"
    base = dict(
        id=1,
        slug="demo",
        filename="services/demo/v1.lua",
        sha256=hashlib.sha256(code.encode()).hexdigest(),
        current_version=1,
        lock_version=0,
        settings={},
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _mngr(tmp_path, row) -> SystemScriptsMngr:
    mngr = SystemScriptsMngr(session=FakeSession(), scripts_dir=str(tmp_path))
    mngr.by_id = _async_returning(row)  # noqa: SLF001 — подмена для юнит-теста
    return mngr


def _async_returning(value):
    async def _fn(*_a, **_kw):
        return value

    return _fn


@pytest.mark.asyncio
async def test_patch_creates_new_version_and_bumps_lock_version(tmp_path):
    row = _script_row()
    mngr = _mngr(tmp_path, row)
    (tmp_path / "services" / "demo").mkdir(parents=True)
    (tmp_path / row.filename).write_text("old code", encoding="utf-8")

    data = SimpleNamespace(code="new code", settings=None, commit_message="v2", lock_version=None)
    updated = await mngr.patch(1, data, actor_id=7)

    assert updated.current_version == 2
    assert updated.lock_version == 1
    assert updated.filename == "services/demo/v2.lua"
    assert (tmp_path / updated.filename).read_text(encoding="utf-8") == "new code"
    version_rows = [o for o in mngr.s.added if isinstance(o, LuaScriptVersionModel)]
    assert len(version_rows) == 1 and version_rows[0].version == 2


@pytest.mark.asyncio
async def test_patch_with_identical_code_is_a_dedup_noop(tmp_path):
    code = "return { handle = function(ctx) end }"
    row = _script_row()  # sha256 уже посчитан от этого же code
    mngr = _mngr(tmp_path, row)

    data = SimpleNamespace(code=code, settings=None, commit_message=None, lock_version=None)
    updated = await mngr.patch(1, data)

    assert updated.current_version == 1
    assert updated.lock_version == 0
    assert mngr.s.added == []  # ни одна версия не создана — контент не изменился


@pytest.mark.asyncio
async def test_patch_with_stale_lock_version_conflicts(tmp_path):
    row = _script_row(lock_version=3)
    mngr = _mngr(tmp_path, row)

    data = SimpleNamespace(code="x", settings=None, commit_message=None, lock_version=1)
    with pytest.raises(HTTPException) as exc:
        await mngr.patch(1, data)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_activate_version_rolls_back_without_new_file(tmp_path):
    row = _script_row(current_version=2, filename="services/demo/v2.lua")
    mngr = _mngr(tmp_path, row)
    v1 = LuaScriptVersionModel(
        script_id=1, version=1, filename="services/demo/v1.lua", sha256="abc"
    )
    mngr.get_version = _async_returning(v1)

    updated = await mngr.activate_version(1, 1, actor_id=5)
    assert updated.current_version == 1
    assert updated.filename == "services/demo/v1.lua"
    assert updated.sha256 == "abc"
    assert updated.lock_version == 1


@pytest.mark.asyncio
async def test_activate_missing_version_404(tmp_path):
    row = _script_row()
    mngr = _mngr(tmp_path, row)
    mngr.get_version = _async_returning(None)

    with pytest.raises(HTTPException) as exc:
        await mngr.activate_version(1, 99)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_activate_stale_lock_version_conflicts(tmp_path):
    row = _script_row(lock_version=2)
    mngr = _mngr(tmp_path, row)
    mngr.get_version = _async_returning(
        LuaScriptVersionModel(script_id=1, version=1, filename="x", sha256="y")
    )

    with pytest.raises(HTTPException) as exc:
        await mngr.activate_version(1, 1, expected_lock_version=0)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_diff_reads_both_versions_and_builds_unified_diff(tmp_path):
    row = _script_row()
    mngr = _mngr(tmp_path, row)
    (tmp_path / "services").mkdir()
    (tmp_path / "services" / "v1.lua").write_text("line a\n", encoding="utf-8")
    (tmp_path / "services" / "v2.lua").write_text("line b\n", encoding="utf-8")

    v1 = LuaScriptVersionModel(script_id=1, version=1, filename="services/v1.lua")
    v2 = LuaScriptVersionModel(script_id=1, version=2, filename="services/v2.lua")

    async def _get_version(_script_id, version):
        return v1 if version == 1 else v2

    mngr.get_version = _get_version

    lines = await mngr.diff(1, 1, 2)
    text = "".join(lines)
    assert "-line a" in text
    assert "+line b" in text


@pytest.mark.asyncio
async def test_diff_missing_version_404(tmp_path):
    row = _script_row()
    mngr = _mngr(tmp_path, row)
    mngr.get_version = _async_returning(None)

    with pytest.raises(HTTPException) as exc:
        await mngr.diff(1, 1, 2)
    assert exc.value.status_code == 404
