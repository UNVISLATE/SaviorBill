"""Админ: управление OAuth-провайдерами (/api/v1/admin/oauth).

Провайдер исполняется Lua-скриптом вида ``auth`` (start/callback). Секреты
провайдера хранятся зашифрованными в ``secrets_enc``.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.db import get_db_session
from dependencies.oauth import get_secbox
from dependencies.rbac import require_perm
from enums import ScriptKind
from models.oauth_providers import OAuthProvidersModel
from models.system_scripts import SystemScriptsModel
from schemas.oauth_provider import (
    OAuthProviderCreate,
    OAuthProvider,
    OAuthProviderPatch,
)
from utils.apidoc import with_fields
from utils.sec.box import SecBox

router = APIRouter()


async def _require_auth_script(session: AsyncSession, script_id: int) -> None:
    """Проверить, что скрипт существует и это активный auth-скрипт."""
    script = await session.get(SystemScriptsModel, script_id)
    if script is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "скрипт не найден")
    if script.kind != ScriptKind.AUTH:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "скрипт должен быть вида auth")


@router.get(
    "/oauth",
    response_model=list[OAuthProvider],
    dependencies=[Depends(require_perm("oauth.read"))],
    summary="Список OAuth-провайдеров (вкл. отключённые)",
)
async def list_providers(
    session: AsyncSession = Depends(get_db_session),
) -> list[OAuthProvider]:
    rows = await session.scalars(
        select(OAuthProvidersModel).order_by(OAuthProvidersModel.id)
    )
    return [OAuthProvider.from_model(r) for r in rows]


@router.post(
    "/oauth",
    response_model=OAuthProvider,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_perm("oauth.create"))],
    summary="Добавить OAuth-провайдера",
    description=with_fields(
        "Создаёт OAuth-провайдера на auth-скрипте; секреты хранятся зашифрованными.",
        OAuthProviderCreate,
    ),
)
async def create_provider(
    body: OAuthProviderCreate,
    session: AsyncSession = Depends(get_db_session),
    box: SecBox = Depends(get_secbox),
) -> OAuthProvider:
    if await session.scalar(
        select(OAuthProvidersModel).where(OAuthProvidersModel.slug == body.slug)
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, "slug провайдера занят")
    await _require_auth_script(session, body.script_id)
    cfg = OAuthProvidersModel(
        slug=body.slug,
        title=body.title,
        enabled=body.enabled,
        script_id=body.script_id,
        secrets_enc=box.seal(json.dumps(body.secrets)),
        scopes=body.scopes,
        extra=body.extra,
    )
    session.add(cfg)
    await session.commit()
    return OAuthProvider.from_model(cfg)


@router.patch(
    "/oauth/{provider_id}",
    response_model=OAuthProvider,
    dependencies=[Depends(require_perm("oauth.edit"))],
    summary="Изменить OAuth-провайдера",
    description=with_fields(
        "Частично обновляет OAuth-провайдера — передаются только изменяемые поля.",
        OAuthProviderPatch,
    ),
)
async def update_provider(
    provider_id: int,
    body: OAuthProviderPatch,
    session: AsyncSession = Depends(get_db_session),
    box: SecBox = Depends(get_secbox),
) -> OAuthProvider:
    cfg = await session.get(OAuthProvidersModel, provider_id)
    if cfg is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "провайдер не найден")
    data = body.model_dump(exclude_unset=True)
    if data.get("script_id") is not None:
        await _require_auth_script(session, data["script_id"])
    if "secrets" in data:
        cfg.secrets_enc = box.seal(json.dumps(data.pop("secrets") or {}))
    for field, value in data.items():
        setattr(cfg, field, value)
    await session.commit()
    return OAuthProvider.from_model(cfg)


@router.delete(
    "/oauth/{provider_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_perm("oauth.delete"))],
    summary="Удалить OAuth-провайдера",
)
async def delete_provider(
    provider_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """Удалить провайдера. Привязки пользователей (oauth_conns) остаются как есть."""
    cfg = await session.get(OAuthProvidersModel, provider_id)
    if cfg is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "провайдер не найден")
    await session.delete(cfg)
    await session.commit()


__all__ = ["router"]
