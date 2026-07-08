"""Админ: роли и каталог прав (RBAC)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.db import get_db_session
from dependencies.rbac import require_perm
from models.roles import Role as RoleModel
from models.user import UserModel
from schemas.role import PermsCatalog, RoleCreate, Role, RolePatch
from services.audit import audit
from utils.apidoc import with_fields
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
    summary="Создать роль",
    description=with_fields(
        "Создаёт роль с набором прав.",
        RoleCreate,
    ),
)
async def create_role(
    request: Request,
    body: RoleCreate,
    session: AsyncSession = Depends(get_db_session),
    acc: UserModel = Depends(require_perm("roles.create")),
) -> Role:
    if await session.scalar(select(RoleModel).where(RoleModel.name == body.name)):
        raise HTTPException(status.HTTP_409_CONFLICT, "роль с таким именем уже есть")
    role = RoleModel(name=body.name, title=body.title, perms=body.perms)
    session.add(role)
    await session.flush()
    await audit(
        session,
        action="role.create",
        actor_id=acc.id,
        actor_role=acc.role.name if acc.role else None,
        target_type="role",
        target_id=str(role.id),
        ip=request.client.host if request.client else None,
        meta={"name": role.name},
    )
    await session.commit()
    return Role.from_model(role)


@router.patch(
    "/roles/{role_id}",
    response_model=Role,
    summary="Изменить роль",
    description=with_fields(
        "Частично обновляет роль — передаются только изменяемые поля. "
        "Права (`perms`) системных ролей (`is_system=true`) менять можно так же, "
        "как и у обычных — системность защищает только сам факт существования "
        "и стабильный `key` роли, не набор прав.",
        RolePatch,
    ),
)
async def update_role(
    request: Request,
    role_id: int,
    body: RolePatch,
    session: AsyncSession = Depends(get_db_session),
    acc: UserModel = Depends(require_perm("roles.edit")),
) -> Role:
    role = await session.get(RoleModel, role_id)
    if role is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "роль не найдена")
    data = body.model_dump(exclude_unset=True)
    if "title" in data:
        role.title = data["title"]
    if "perms" in data:
        role.perms = data["perms"]
    await audit(
        session,
        action="role.update",
        actor_id=acc.id,
        actor_role=acc.role.name if acc.role else None,
        target_type="role",
        target_id=str(role_id),
        ip=request.client.host if request.client else None,
        meta={"fields": sorted(data.keys())},
    )
    await session.commit()
    return Role.from_model(role)


__all__ = ["router"]
