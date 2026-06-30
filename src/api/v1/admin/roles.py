"""Админ: роли и каталог прав (RBAC)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.db import get_db_session
from dependencies.rbac import require_perm
from models.roles import Role as RoleModel
from schemas.role import PermsCatalog, RoleCreate, Role, RolePatch
from utils.rbac import all_perms, perms_tree

router = APIRouter()


@router.get(
    "/perms",
    response_model=PermsCatalog,
    dependencies=[Depends(require_perm("roles.read"))],
    summary="Каталог прав",
    description=(
        "Все объявленные в приложении права (плоский список и дерево) — для "
        "удобного назначения ролям из админ-панели."
    ),
)
async def perms_catalog() -> PermsCatalog:
    return PermsCatalog(flat=all_perms(), tree=perms_tree())


@router.get(
    "/roles",
    response_model=list[Role],
    dependencies=[Depends(require_perm("roles.read"))],
    summary="Список ролей",
)
async def list_roles(session: AsyncSession = Depends(get_db_session)) -> list[Role]:
    rows = await session.scalars(select(RoleModel).order_by(RoleModel.id))
    return [Role.from_model(r) for r in rows]


@router.post(
    "/roles",
    response_model=Role,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_perm("roles.edit"))],
    summary="Создать роль",
)
async def create_role(
    body: RoleCreate, session: AsyncSession = Depends(get_db_session)
) -> Role:
    if await session.scalar(select(RoleModel).where(RoleModel.name == body.name)):
        raise HTTPException(status.HTTP_409_CONFLICT, "роль с таким именем уже есть")
    role = RoleModel(name=body.name, title=body.title, perms=body.perms)
    session.add(role)
    await session.commit()
    return Role.from_model(role)


@router.patch(
    "/roles/{role_id}",
    response_model=Role,
    dependencies=[Depends(require_perm("roles.edit"))],
    summary="Изменить роль",
)
async def update_role(
    role_id: int, body: RolePatch, session: AsyncSession = Depends(get_db_session)
) -> Role:
    role = await session.get(RoleModel, role_id)
    if role is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "роль не найдена")
    if role.is_system:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "системную роль менять нельзя")
    data = body.model_dump(exclude_unset=True)
    if "title" in data:
        role.title = data["title"]
    if "perms" in data:
        role.perms = data["perms"]
    await session.commit()
    return Role.from_model(role)


__all__ = ["router"]
