"""Админ: управление OAuth-провайдерами (/api/v1/admin/oauth)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.db import get_db_session
from dependencies.oauth import get_secbox
from dependencies.rbac import require_perm
from models.oauth_cfg import OAuthCfg
from schemas.admin import OAuthCfgIn, OAuthCfgOut, OAuthCfgPatch
from utils.sec.box import SecBox

router = APIRouter()


@router.get(
    "/oauth",
    response_model=list[OAuthCfgOut],
    dependencies=[Depends(require_perm("oauth.read"))],
    summary="Список OAuth-провайдеров (вкл. отключённые)",
)
async def list_providers(
    session: AsyncSession = Depends(get_db_session),
) -> list[OAuthCfg]:
    rows = await session.scalars(select(OAuthCfg).order_by(OAuthCfg.id))
    return list(rows)


@router.post(
    "/oauth",
    response_model=OAuthCfgOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_perm("oauth.edit"))],
    summary="Добавить OAuth-провайдера",
)
async def create_provider(
    body: OAuthCfgIn,
    session: AsyncSession = Depends(get_db_session),
    box: SecBox = Depends(get_secbox),
) -> OAuthCfg:
    if await session.scalar(select(OAuthCfg).where(OAuthCfg.slug == body.slug)):
        raise HTTPException(status.HTTP_409_CONFLICT, "slug провайдера занят")
    cfg = OAuthCfg(
        slug=body.slug,
        title=body.title,
        enabled=body.enabled,
        client_id=body.client_id,
        client_secret_enc=box.seal(body.client_secret),
        issuer=body.issuer,
        authorize_url=body.authorize_url,
        token_url=body.token_url,
        userinfo_url=body.userinfo_url,
        jwks_uri=body.jwks_uri,
        scopes=body.scopes,
        extra=body.extra,
    )
    session.add(cfg)
    await session.commit()
    return cfg


@router.patch(
    "/oauth/{provider_id}",
    response_model=OAuthCfgOut,
    dependencies=[Depends(require_perm("oauth.edit"))],
    summary="Изменить OAuth-провайдера",
)
async def update_provider(
    provider_id: int,
    body: OAuthCfgPatch,
    session: AsyncSession = Depends(get_db_session),
    box: SecBox = Depends(get_secbox),
) -> OAuthCfg:
    cfg = await session.get(OAuthCfg, provider_id)
    if cfg is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "провайдер не найден")
    data = body.model_dump(exclude_unset=True)
    if "client_secret" in data:
        cfg.client_secret_enc = box.seal(data.pop("client_secret"))
    for field, value in data.items():
        setattr(cfg, field, value)
    await session.commit()
    return cfg


__all__ = ["router"]
