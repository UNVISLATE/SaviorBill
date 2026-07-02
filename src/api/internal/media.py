"""Внутренние медиа-роуты для mediaworker (/internal/media, service-token).

- authorize: mediaworker спрашивает, может ли пользователь загрузить и какой объём;
- register: mediaworker после конвертации фиксирует готовое медиа в БД.

Роуты скрыты из публичного Swagger (``include_in_schema=False``) и защищены
сервисным токеном.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from dependencies.auth import get_acc_mngr
from dependencies.internal import require_service_token
from dependencies.media import get_media_mngr
from models.system_media import SystemMediaMngr
from models.user import UserMngr
from schemas.media import Media, MediaAuthz, MediaAuthzReq, MediaRegister
from utils.config import AppConfig
from utils.rbac import has_perm, reg_perm
from utils.sec import jwt as jwtu

router = APIRouter(
    prefix="/media",
    dependencies=[Depends(require_service_token)],
    include_in_schema=False,
)

# Права, по которым определяется допустимый объём загрузки.
_PERM_SMALL = reg_perm("media.upload")
_PERM_LARGE = reg_perm("media.uploadlarge")

_KINDS = {"image", "video", "icon", "avatar"}


@router.post("/authorize", response_model=MediaAuthz)
async def authorize(
    request: Request,
    body: MediaAuthzReq,
    mngr: UserMngr = Depends(get_acc_mngr),
) -> MediaAuthz:
    """Авторизовать загрузку по access-JWT пользователя и вернуть лимит объёма."""
    cfg: AppConfig = request.app.state.settings
    if body.kind not in _KINDS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "недопустимый вид медиа")

    try:
        claims = jwtu.decode_jwt(
            body.user_token, cfg.JWT_SECRET, cfg.JWT_ALG, cfg.JWT_ISS
        )
    except jwtu.InvalidJWT as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
    if claims.typ != jwtu.ACCESS:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "access_token expected")

    acc = await mngr.by_id(int(claims.sub))
    if acc is None or not acc.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "access denied")

    perms = acc.role.perms if acc.role else None
    if has_perm(perms, _PERM_LARGE):
        max_bytes = cfg.MEDIA_MAX_BYTES
    elif has_perm(perms, _PERM_SMALL):
        max_bytes = cfg.MEDIA_SMALL_MAX_BYTES
    else:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail=f"недостаточно прав: {_PERM_SMALL}"
        )
    return MediaAuthz(owner_id=acc.id, max_bytes=max_bytes)


@router.post("/register", response_model=Media)
async def register(
    body: MediaRegister,
    mngr: SystemMediaMngr = Depends(get_media_mngr),
) -> Media:
    """Зафиксировать готовое (сконвертированное) медиа в БД."""
    existing = await mngr.by_token(body.token)
    if existing is not None:
        return Media.from_model(existing)  # идемпотентность
    media = await mngr.create(
        body.kind,
        body.path,
        token=body.token,
        status="ready",
        backend=body.backend,
        mime=body.mime,
        size=body.size,
        owner_id=body.owner_id,
    )
    await mngr.s.commit()
    return Media.from_model(media)


__all__ = ["router"]
