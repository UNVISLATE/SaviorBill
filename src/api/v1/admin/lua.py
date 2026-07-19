"""Админ: управление Lua-скриптами (/api/v1/admin/lua)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from dependencies.catalog import SystemScriptsMngr, get_script_mngr
from dependencies.rbac import require_perm
from models.user import UserModel
from lua.schemas import LuaScript, LuaScriptDetail, LuaScriptUpload, LuaScriptPatch
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
    mngr: SystemScriptsMngr = Depends(get_script_mngr),
) -> LuaScriptDetail:
    row = await mngr.by_id(script_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "script not found")
    code = await mngr.read_code(row)
    return LuaScriptDetail.from_model_with_code(row, code)


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
    row = await mngr.create(body)
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
    row = await mngr.patch(script_id, body)
    await audit(
        mngr.s,
        action="lua.edit",
        target_type="lua_script",
        target_id=str(script_id),
        **_actor(request, acc),
    )
    await mngr.s.commit()
    return LuaScript.from_model(row)


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
