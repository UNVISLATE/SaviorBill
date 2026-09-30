"""Админ: роли и каталог прав (RBAC)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.db import get_db_session
from dependencies.rbac import require_perm
from models.roles import Role as RoleModel
from models.user import UserModel
from schemas.role import PermsCatalog, RoleCreate, Role, RoleImpact, RolePatch
from services.audit import audit
from security.owner_guard import assert_role_editable
from security.rbac import all_perms, perms_tree

router = APIRouter()


@router.get(
    "/perms",
    response_model=PermsCatalog,
    dependencies=[Depends(require_perm("roles.read"))],
    summary="Permissions catalog",
    description="List all available permissions for roles.",
)
async def perms_catalog() -> PermsCatalog:
    return PermsCatalog(flat=all_perms(), tree=perms_tree())


@router.get(
    "/roles",
    response_model=list[Role],
    dependencies=[Depends(require_perm("roles.read"))],
    summary="Roles",
)
async def list_roles(session: AsyncSession = Depends(get_db_session)) -> list[Role]:
    rows = await session.scalars(select(RoleModel).order_by(RoleModel.id))
    return [Role.from_model(r) for r in rows]


@router.post(
    "/roles",
    response_model=Role,
    status_code=status.HTTP_201_CREATED,
    summary="Create role",
    description="Create a role.",
)
async def create_role(
    request: Request,
    body: RoleCreate,
    session: AsyncSession = Depends(get_db_session),
    acc: UserModel = Depends(require_perm("roles.create")),
) -> Role:
    if await session.scalar(select(RoleModel).where(RoleModel.name == body.name)):
        raise HTTPException(status.HTTP_409_CONFLICT, "role name already exists")
    role = RoleModel(
        name=body.name,
        title=body.title,
        perms=body.perms,
        admin_login_allowed=body.admin_login_allowed,
        allow_login=body.allow_login,
    )
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
    summary="Update role",
    description="Update a role.",
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
        raise HTTPException(status.HTTP_404_NOT_FOUND, "role not found")
    assert_role_editable(role)
    data = body.model_dump(exclude_unset=True)
    if "title" in data:
        role.title = data["title"]
    if "admin_login_allowed" in data:
        role.admin_login_allowed = data["admin_login_allowed"]
    if "allow_login" in data:
        role.allow_login = data["allow_login"]
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


@router.get(
    "/roles/{role_id}/impact",
    response_model=RoleImpact,
    dependencies=[Depends(require_perm("roles.read"))],
    summary="Role assignment impact",
)
async def role_impact(
    role_id: int, session: AsyncSession = Depends(get_db_session)
) -> RoleImpact:
    role = await session.get(RoleModel, role_id)
    if role is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "role not found")
    assigned = int(
        await session.scalar(
            select(func.count()).select_from(UserModel).where(UserModel.role_id == role_id)
        )
        or 0
    )
    return RoleImpact(
        role_id=role.id,
        assigned_accounts=assigned,
        is_system=role.is_system,
        is_protected=role.is_protected,
        can_delete=not role.is_system and not role.is_protected and assigned == 0,
    )


@router.delete(
    "/roles/{role_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete custom role",
    description="Delete an unassigned custom role. System and protected roles cannot be deleted.",
)
async def delete_role(
    request: Request,
    role_id: int,
    session: AsyncSession = Depends(get_db_session),
    acc: UserModel = Depends(require_perm("roles.delete")),
) -> None:
    role = await session.get(RoleModel, role_id)
    if role is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "role not found")
    if role.is_system or role.is_protected:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "system roles cannot be deleted")
    assigned = int(
        await session.scalar(
            select(func.count()).select_from(UserModel).where(UserModel.role_id == role_id)
        )
        or 0
    )
    if assigned:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"role is assigned to {assigned} account(s); reassign them first",
        )
    await audit(
        session,
        action="role.delete",
        actor_id=acc.id,
        actor_role=acc.role.name if acc.role else None,
        target_type="role",
        target_id=str(role_id),
        ip=request.client.host if request.client else None,
        meta={"name": role.name},
    )
    await session.delete(role)
    await session.commit()


__all__ = ["router"]
