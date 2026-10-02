"""Тесты Этапа C: чтение тела Lua-скрипта (GET /lua/{id})."""

from __future__ import annotations

import hashlib
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from models.system_scripts import SystemScriptsMngr
from lua.schemas import LuaScriptDetail

pytestmark = pytest.mark.unit


def _row(filename: str, **overrides) -> SimpleNamespace:
    base = dict(
        id=1,
        slug="google-auth",
        name="Google Auth",
        kind="auth",
        filename=filename,
        actions=["start", "callback"],
        settings={},
        is_active=True,
        current_version=1,
        lock_version=0,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


class TestSystemScriptsMngrReadCode:
    @pytest.mark.asyncio
    async def test_reads_existing_file(self, tmp_path) -> None:
        (tmp_path / "auth").mkdir()
        (tmp_path / "auth" / "s1.lua").write_text(
            "function handle(ctx) end", encoding="utf-8"
        )
        mngr = SystemScriptsMngr(session=None, scripts_dir=str(tmp_path))
        row = _row("auth/s1.lua")
        code = await mngr.read_code(row)
        assert code == "function handle(ctx) end"

    @pytest.mark.asyncio
    async def test_missing_file_raises_404(self, tmp_path) -> None:
        mngr = SystemScriptsMngr(session=None, scripts_dir=str(tmp_path))
        row = _row("auth/missing.lua")
        with pytest.raises(HTTPException) as exc:
            await mngr.read_code(row)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_rejects_path_escape(self, tmp_path) -> None:
        mngr = SystemScriptsMngr(session=None, scripts_dir=str(tmp_path))
        row = _row("../../etc/passwd")
        with pytest.raises(HTTPException) as exc:
            await mngr.read_code(row)
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_rejects_changed_file_when_hash_is_recorded(self, tmp_path) -> None:
        (tmp_path / "auth").mkdir()
        (tmp_path / "auth" / "s1.lua").write_text("changed", encoding="utf-8")
        mngr = SystemScriptsMngr(session=None, scripts_dir=str(tmp_path))
        row = _row(
            "auth/s1.lua",
            sha256=hashlib.sha256(b"original").hexdigest(),
        )
        with pytest.raises(HTTPException) as exc:
            await mngr.read_code(row)
        assert exc.value.status_code == 409

    @pytest.mark.asyncio
    async def test_artifact_status_distinguishes_missing_and_corrupt(self, tmp_path) -> None:
        (tmp_path / "auth").mkdir()
        target = tmp_path / "auth" / "s1.lua"
        target.write_text("valid", encoding="utf-8")
        mngr = SystemScriptsMngr(session=None, scripts_dir=str(tmp_path))

        assert await mngr.artifact_status("auth/missing.lua") == "missing"
        assert (
            await mngr.artifact_status(
                "auth/s1.lua",
                expected_sha256=hashlib.sha256(b"original").hexdigest(),
            )
            == "corrupt"
        )
        assert (
            await mngr.artifact_status(
                "auth/s1.lua",
                expected_sha256=hashlib.sha256(b"valid").hexdigest(),
            )
            == "ready"
        )

    @pytest.mark.asyncio
    async def test_reconcile_reports_missing_corrupt_and_orphan_files(self, tmp_path) -> None:
        (tmp_path / "auth").mkdir()
        (tmp_path / "auth" / "orphan.lua").write_text("orphan", encoding="utf-8")
        mngr = SystemScriptsMngr(session=None, scripts_dir=str(tmp_path))
        script = _row("auth/missing.lua", id=7, current_version=2)
        mngr.list_all = lambda: _async_value([script])
        mngr.list_versions = lambda _script_id: _async_value([])

        result = await mngr.reconcile_artifacts()

        assert result["checked_scripts"] == 1
        assert result["checked_artifacts"] == 1
        assert result["issues"] == [
            {
                "script_id": 7,
                "version": 2,
                "filename": "auth/missing.lua",
                "status": "missing",
            }
        ]
        assert result["orphan_files"] == ["auth/orphan.lua"]


async def _async_value(value):
    return value


class TestLuaScriptDetailSchema:
    def test_from_model_with_code_includes_body(self) -> None:
        row = _row("auth/s1.lua")
        detail = LuaScriptDetail.from_model_with_code(row, "-- lua code")
        assert detail.code == "-- lua code"
        assert detail.slug == "google-auth"
        assert detail.kind == "auth"
        assert detail.filename == "auth/s1.lua"
        assert detail.actions == ["start", "callback"]
        assert detail.is_active is True

    def test_detail_is_a_lua_script_subclass(self) -> None:
        from lua.schemas import LuaScript

        assert issubclass(LuaScriptDetail, LuaScript)
