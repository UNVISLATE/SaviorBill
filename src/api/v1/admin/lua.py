"""Админ: управление Lua-скриптами (/api/v1/admin/lua)."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request, status
from valkey.asyncio import Valkey

from dependencies.catalog import SystemScriptsMngr, get_script_mngr
from dependencies.rbac import require_perm
from dependencies.valkey import get_valkey_client
from lua.bus import LuaBus, LuaError
from lua.deps import get_lua_bus_configured
from models.user import UserModel
from lua.schemas import (
    LuaScript,
    LuaScriptDetail,
    LuaScriptVersion,
    LuaScriptVersionDetail,
    LuaScriptUpload,
    LuaScriptPatch,
    LuaScriptActivate,
    LuaScriptLint,
    LuaScriptLintResult,
    LuaScriptTestRun,
    LuaScriptTestRunResult,
)
from services.audit import audit

router = APIRouter()


def _actor(request: Request, acc: UserModel) -> dict:
    """Собрать поля актора (id/роль/ip) для аудита."""
    return {
        "actor_id": acc.id,
        "actor_role": acc.role.name if acc.role else None,
        "ip": request.client.host if request.client else None,
    }



@router.get(
    "",
    response_model=list[LuaScript],
    dependencies=[Depends(require_perm("lua.read"))],
    summary="Lua scripts",
)
async def list_scripts(
    mngr: SystemScriptsMngr = Depends(get_script_mngr),
) -> list[LuaScript]:
    rows = await mngr.list_all()
    return [LuaScript.from_model(r) for r in rows]


@router.get(
    "/{script_id}",
    response_model=LuaScriptDetail,
    dependencies=[Depends(require_perm("lua.read"))],
    summary="Get Lua script",
)
async def get_script(
    script_id: int,
    version: int | None = None,
    mngr: SystemScriptsMngr = Depends(get_script_mngr),
) -> LuaScriptDetail:
    row = await mngr.by_id(script_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "script not found")
    if version is None or version == row.current_version:
        code = await mngr.read_code(row)
        return LuaScriptDetail.from_model_with_code(row, code, row.current_version)
    v = await mngr.get_version(script_id, version)
    if v is None:
        # версия не найдена/удалена — тихий фоллбэк на latest
        code = await mngr.read_code(row)
        return LuaScriptDetail.from_model_with_code(row, code, row.current_version)
    code = await mngr.read_code_at(v.filename)
    return LuaScriptDetail.from_model_with_code(row, code, v.version)


@router.get(
    "/{script_id}/versions",
    response_model=list[LuaScriptVersion],
    dependencies=[Depends(require_perm("lua.read"))],
    summary="List Lua script versions",
)
async def list_script_versions(
    script_id: int,
    mngr: SystemScriptsMngr = Depends(get_script_mngr),
) -> list[LuaScriptVersion]:
    row = await mngr.by_id(script_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "script not found")
    rows = await mngr.list_versions(script_id)
    return [LuaScriptVersion.from_model(v) for v in rows]


@router.get(
    "/{script_id}/versions/{version}",
    response_model=LuaScriptVersionDetail,
    dependencies=[Depends(require_perm("lua.read"))],
    summary="Get Lua script version body",
)
async def get_script_version(
    script_id: int,
    version: int,
    mngr: SystemScriptsMngr = Depends(get_script_mngr),
) -> LuaScriptVersionDetail:
    v = await mngr.get_version(script_id, version)
    if v is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "version not found")
    code = await mngr.read_code_at(v.filename)
    return LuaScriptVersionDetail(
        version=v.version,
        sha256=v.sha256,
        commit_message=v.commit_message,
        created_at=v.created_at.isoformat(),
        created_by=v.created_by,
        code=code,
    )


@router.post(
    "",
    response_model=LuaScript,
    status_code=status.HTTP_201_CREATED,
    summary="Upload Lua script",
    description="Upload a Lua script and register it.",
)
async def upload_script(
    request: Request,
    body: LuaScriptUpload,
    mngr: SystemScriptsMngr = Depends(get_script_mngr),
    acc: UserModel = Depends(require_perm("lua.create")),
) -> LuaScript:
    row = await mngr.create(body, created_by=acc.id)
    await audit(
        mngr.s,
        action="lua.upload",
        target_type="lua_script",
        target_id=str(row.id),
        meta={"name": getattr(row, "name", None)},
        **_actor(request, acc),
    )
    await mngr.s.commit()
    return LuaScript.from_model(row)


@router.patch(
    "/{script_id}",
    response_model=LuaScript,
    summary="Update Lua script",
    description="Update a Lua script.",
)
async def edit_script(
    request: Request,
    script_id: int,
    body: LuaScriptPatch,
    mngr: SystemScriptsMngr = Depends(get_script_mngr),
    acc: UserModel = Depends(require_perm("lua.edit")),
) -> LuaScript:
    row = await mngr.patch(script_id, body, actor_id=acc.id)
    await audit(
        mngr.s,
        action="lua.edit",
        target_type="lua_script",
        target_id=str(script_id),
        meta={
            "version": row.current_version,
            "sha256": row.sha256,
            "commit_message": body.commit_message,
        },
        **_actor(request, acc),
    )
    await mngr.s.commit()
    return LuaScript.from_model(row)


@router.post(
    "/{script_id}/versions/{version}/activate",
    response_model=LuaScript,
    summary="Activate an existing script version (rollback)",
    description="Point current_version at an already-stored historical version, without creating a new file.",
)
async def activate_script_version(
    request: Request,
    script_id: int,
    version: int,
    body: LuaScriptActivate,
    mngr: SystemScriptsMngr = Depends(get_script_mngr),
    acc: UserModel = Depends(require_perm("lua.edit")),
) -> LuaScript:
    row = await mngr.activate_version(
        script_id, version, actor_id=acc.id, expected_lock_version=body.lock_version
    )
    await audit(
        mngr.s,
        action="lua.activate_version",
        target_type="lua_script",
        target_id=str(script_id),
        meta={"version": row.current_version, "sha256": row.sha256},
        **_actor(request, acc),
    )
    await mngr.s.commit()
    return LuaScript.from_model(row)


@router.get(
    "/{script_id}/diff",
    dependencies=[Depends(require_perm("lua.read"))],
    summary="Diff between two versions of a script",
)
async def diff_script_versions(
    script_id: int,
    from_version: int,
    to_version: int,
    mngr: SystemScriptsMngr = Depends(get_script_mngr),
) -> dict:
    lines = await mngr.diff(script_id, from_version, to_version)
    return {"diff": "".join(lines)}


@router.post(
    "/lint",
    response_model=LuaScriptLintResult,
    dependencies=[Depends(require_perm("lua.edit"))],
    summary="Compile-check Lua code (no side effects)",
)
async def lint_script(
    body: LuaScriptLint,
    bus: LuaBus = Depends(get_lua_bus_configured),
) -> LuaScriptLintResult:
    try:
        res = await bus.call("lint", {"code": body.code})
    except LuaError as exc:
        return LuaScriptLintResult(ok=False, error=str(exc))
    return LuaScriptLintResult(ok=bool(res.get("ok")), error=res.get("error"))


@router.post(
    "/{script_id}/test-run",
    response_model=LuaScriptTestRunResult,
    summary="Sandboxed test-run (http/billing stubbed, no side effects)",
)
async def test_run_script(
    script_id: int,
    body: LuaScriptTestRun,
    mngr: SystemScriptsMngr = Depends(get_script_mngr),
    bus: LuaBus = Depends(get_lua_bus_configured),
    acc: UserModel = Depends(require_perm("lua.test")),
) -> LuaScriptTestRunResult:
    row = await mngr.by_id(script_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "script not found")
    code = body.code if body.code is not None else await mngr.read_code(row)
    try:
        res = await bus.call(
            "run_script_sandbox",
            {"code": code, "ctx": body.ctx or {}},
            metric_label=f"test_run:{row.slug}",
        )
    except LuaError as exc:
        return LuaScriptTestRunResult(error=str(exc))
    return LuaScriptTestRunResult(
        public=res.get("public") or {},
        private=res.get("private") or {},
        logs=res.get("logs") or [],
    )


@router.get(
    "/executions/{cid}/logs",
    dependencies=[Depends(require_perm("lua.read"))],
    summary="Read the execution log of a script run by its correlation id",
    description="Reads lua:log:{cid} in Valkey (short-lived, see luaworker main.lua LOG_TTL).",
)
async def get_execution_logs(
    cid: str,
    vk: Valkey = Depends(get_valkey_client),
) -> dict:
    raw = await vk.get(f"lua:log:{cid}")
    if raw is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "no logs found for this cid (expired or never produced any log lines)",
        )
    return {"cid": cid, "logs": json.loads(raw)}


@router.delete(
    "/{script_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Lua script",
)
async def delete_script(
    request: Request,
    script_id: int,
    mngr: SystemScriptsMngr = Depends(get_script_mngr),
    acc: UserModel = Depends(require_perm("lua.delete")),
) -> None:
    await mngr.delete(script_id)
    await audit(
        mngr.s,
        action="lua.delete",
        target_type="lua_script",
        target_id=str(script_id),
        **_actor(request, acc),
    )
    await mngr.s.commit()


__all__ = ["router"]
