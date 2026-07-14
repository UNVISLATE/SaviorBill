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
from dependencies.media import get_media_mngr
from dependencies.oauth import get_secbox
from dependencies.rbac import require_perm
from enums import ScriptKind
from models.oauth_providers import OAuthProvidersModel
from models.system_media import SystemMediaMngr
from models.system_scripts import SystemScriptsModel
from schemas.oauth_provider import (
    OAuthProviderCreate,
    OAuthProvider,
    OAuthProviderPatch,
)
from utils.sec.box import SecBox

router = APIRouter()


async def _require_auth_script(session: AsyncSession, script_id: int) -> None:
    """Проверить, что скрипт существует и это активный auth-скрипт."""
    script = await session.get(SystemScriptsModel, script_id)
    if script is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "script not found")
    if script.kind != ScriptKind.AUTH:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "script must be auth")


async def _require_media(mngr: SystemMediaMngr, media_id: int) -> None:
    """Проверить, что медиа для иконки провайдера существует."""
    if await mngr.by_id(media_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "media not found")


@router.get(
    "",
    response_model=list[OAuthProvider],
    dependencies=[Depends(require_perm("oauth.read"))],
    summary="OAuth providers",
)
async def list_providers(
    session: AsyncSession = Depends(get_db_session),
) -> list[OAuthProvider]:
    rows = await session.scalars(
        select(OAuthProvidersModel).order_by(OAuthProvidersModel.id)
    )
    return [OAuthProvider.from_model(r) for r in rows]


@router.get(
    "/{provider_id}",
    response_model=OAuthProvider,
    dependencies=[Depends(require_perm("oauth.read"))],
    summary="Get OAuth provider",
)
async def get_provider(
    provider_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> OAuthProvider:
    cfg = await session.get(OAuthProvidersModel, provider_id)
    if cfg is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "provider not found")
    return OAuthProvider.from_model(cfg)


@router.post(
    "",
    response_model=OAuthProvider,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_perm("oauth.create"))],
    summary="Create OAuth provider",
    description="Create an OAuth provider with encrypted secrets.",
)
async def create_provider(
    body: OAuthProviderCreate,
    session: AsyncSession = Depends(get_db_session),
    box: SecBox = Depends(get_secbox),
    media: SystemMediaMngr = Depends(get_media_mngr),
) -> OAuthProvider:
    if await session.scalar(
        select(OAuthProvidersModel).where(OAuthProvidersModel.slug == body.slug)
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, "provider slug already exists")
    await _require_auth_script(session, body.script_id)
    if body.icon_media_id is not None:
        await _require_media(media, body.icon_media_id)
    cfg = OAuthProvidersModel(
        slug=body.slug,
        title=body.title,
        enabled=body.enabled,
        script_id=body.script_id,
        secrets_enc=box.seal(json.dumps(body.secrets)),
        icon_media_id=body.icon_media_id,
        scopes=body.scopes,
        extra=body.extra,
    )
    session.add(cfg)
    await session.commit()
    return OAuthProvider.from_model(cfg)


@router.patch(
    "/{provider_id}",
    response_model=OAuthProvider,
    dependencies=[Depends(require_perm("oauth.edit"))],
    summary="Update OAuth provider",
    description="Update an OAuth provider.",
)
async def update_provider(
    provider_id: int,
    body: OAuthProviderPatch,
    session: AsyncSession = Depends(get_db_session),
    box: SecBox = Depends(get_secbox),
    media: SystemMediaMngr = Depends(get_media_mngr),
) -> OAuthProvider:
    cfg = await session.get(OAuthProvidersModel, provider_id)
    if cfg is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "provider not found")
    data = body.model_dump(exclude_unset=True)
    if data.get("script_id") is not None:
        await _require_auth_script(session, data["script_id"])
    if data.get("icon_media_id") is not None:
        await _require_media(media, data["icon_media_id"])
    if "secrets" in data:
        cfg.secrets_enc = box.seal(json.dumps(data.pop("secrets") or {}))
    for field, value in data.items():
        setattr(cfg, field, value)
    await session.commit()
    return OAuthProvider.from_model(cfg)


@router.delete(
    "/{provider_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_perm("oauth.delete"))],
    summary="Delete OAuth provider",
)
async def delete_provider(
    provider_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """Удалить провайдера. Привязки пользователей (oauth_conns) остаются как есть."""
    cfg = await session.get(OAuthProvidersModel, provider_id)
    if cfg is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "provider not found")
    await session.delete(cfg)
    await session.commit()


__all__ = ["router"]
