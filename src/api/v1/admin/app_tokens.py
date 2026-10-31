"""API управления токенами приложений (App Tokens)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.db import get_db_session
from dependencies.rbac import require_perm
from models.app_tokens import AppTokensMngr
from models.user import UserModel
from schemas.app_tokens import AppToken, AppTokenCreate, AppTokenCreated
from services.audit import audit

router = APIRouter()


@router.get(
    "",
    response_model=list[AppToken],
    dependencies=[Depends(require_perm("apptokens.read"))],
    summary="List app tokens",
    description="Список всех созданных токенов приложений (без секретов).",
)
async def list_app_tokens(
    session: AsyncSession = Depends(get_db_session),
) -> list[AppToken]:
    mngr = AppTokensMngr(session)
    tokens = await mngr.list_tokens()
    return [AppToken.model_validate(t) for t in tokens]


@router.get(
    "/{token_id}",
    response_model=AppToken,
    dependencies=[Depends(require_perm("apptokens.read"))],
    summary="Get app token details",
)
async def get_app_token(
    token_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> AppToken:
    mngr = AppTokensMngr(session)
    token = await mngr.by_id(token_id)
    if not token:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "app token not found")
    return AppToken.model_validate(token)


@router.post(
    "",
    response_model=AppTokenCreated,
    status_code=status.HTTP_201_CREATED,
    summary="Create app token",
    description="Выпустить новый токен приложения. Секрет возвращается СТРОГО ОДИН РАЗ.",
)
async def create_app_token(
    request: Request,
    body: AppTokenCreate,
    session: AsyncSession = Depends(get_db_session),
    caller: UserModel = Depends(require_perm("apptokens.create")),
) -> AppTokenCreated:
    mngr = AppTokensMngr(session)
    token, secret_token = await mngr.create(
        name=body.name,
        description=body.description,
        permissions=body.permissions,
        ip_allowlist=body.ip_allowlist,
        created_by_account_id=caller.id,
        expires_at=body.expires_at,
    )
    await audit(
        session,
        action="app_token.create",
        actor_id=caller.id,
        target_type="app_token",
        target_id=str(token.id),
        meta={"name": token.name, "prefix": token.token_prefix, "permissions": token.permissions},
    )
    await session.commit()
    return AppTokenCreated(
        **AppToken.model_validate(token).model_dump(),
        secret_token=secret_token,
    )


@router.post(
    "/{token_id}/revoke",
    response_model=AppToken,
    summary="Revoke app token",
    description="Отозвать и заблокировать токен приложения.",
)
async def revoke_app_token(
    token_id: int,
    session: AsyncSession = Depends(get_db_session),
    caller: UserModel = Depends(require_perm("apptokens.revoke")),
) -> AppToken:
    mngr = AppTokensMngr(session)
    token = await mngr.revoke(token_id, caller.id)
    if not token:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "app token not found")
    await audit(
        session,
        action="app_token.revoke",
        actor_id=caller.id,
        target_type="app_token",
        target_id=str(token.id),
        meta={"name": token.name, "prefix": token.token_prefix},
    )
    await session.commit()
    return AppToken.model_validate(token)


@router.delete(
    "/{token_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete app token",
    description="Удалить токен приложения из системы.",
)
async def delete_app_token(
    token_id: int,
    session: AsyncSession = Depends(get_db_session),
    caller: UserModel = Depends(require_perm("apptokens.delete")),
) -> Response:
    mngr = AppTokensMngr(session)
    token = await mngr.by_id(token_id)
    if not token:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "app token not found")
    await mngr.delete(token_id)
    await audit(
        session,
        action="app_token.delete",
        actor_id=caller.id,
        target_type="app_token",
        target_id=str(token_id),
        meta={"name": token.name, "prefix": token.token_prefix},
    )
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]
