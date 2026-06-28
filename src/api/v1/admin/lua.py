"""Админ: управление Lua-скриптами (/api/v1/admin/lua)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from dependencies.catalog import ScriptMngr, get_script_mngr
from dependencies.rbac import require_perm
from schemas.catalog import ScriptIn, ScriptOut, ScriptPatch

router = APIRouter()


@router.get(
    "/lua",
    response_model=list[ScriptOut],
    dependencies=[Depends(require_perm("lua.read"))],
    summary="Список Lua-скриптов",
)
async def list_scripts(mngr: ScriptMngr = Depends(get_script_mngr)) -> list[ScriptOut]:
    return await mngr.list_all()


@router.post(
    "/lua",
    response_model=ScriptOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_perm("lua.edit"))],
    summary="Загрузить Lua-скрипт",
    description="Сохраняет тело скрипта в монтируемую папку и регистрирует в БД.",
)
async def upload_script(
    body: ScriptIn, mngr: ScriptMngr = Depends(get_script_mngr)
) -> ScriptOut:
    row = await mngr.create(body)
    await mngr.s.commit()
    return row


@router.patch(
    "/lua/{script_id}",
    response_model=ScriptOut,
    dependencies=[Depends(require_perm("lua.edit"))],
    summary="Изменить тело Lua-скрипта",
)
async def edit_script(
    script_id: int,
    body: ScriptPatch,
    mngr: ScriptMngr = Depends(get_script_mngr),
) -> ScriptOut:
    row = await mngr.update_code(script_id, body.code)
    await mngr.s.commit()
    return row


@router.delete(
    "/lua/{script_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_perm("lua.edit"))],
    summary="Удалить Lua-скрипт",
)
async def delete_script(
    script_id: int, mngr: ScriptMngr = Depends(get_script_mngr)
) -> None:
    await mngr.delete(script_id)
    await mngr.s.commit()


__all__ = ["router"]
