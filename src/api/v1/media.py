"""Загрузка медиа-файлов (/api/v1/media)."""

from __future__ import annotations

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)

from dependencies.auth import get_current_acc
from dependencies.media import get_media_mngr, get_storage_svc
from models.system_media import SystemMediaMngr
from models.user import UserModel
from schemas.media import Media
from utils.config import AppConfig
from utils.rbac import has_perm, reg_perm
from utils.storage import StorageSvc

router = APIRouter(prefix="/api/v1/media", tags=["media"])

# Регистрируем оба права в каталоге (для админ-UI), т.к. проверяем их вручную.
_PERM_SMALL = reg_perm("media.upload")
_PERM_LARGE = reg_perm("media.uploadlarge")

# Допустимые виды и их подпапки в хранилище.
_FOLDER_BY_KIND = {
    "image": "images",
    "video": "videos",
    "icon": "icons",
    "avatar": "avatars",
}


@router.post(
    "/upload",
    response_model=Media,
    status_code=status.HTTP_201_CREATED,
    summary="Загрузить медиа-файл",
    description=(
        "Загрузка изображения/видео/иконки/аватарки. Маленькие файлы требуют "
        "права `media.upload`, большие — `media.uploadlarge` (порог и потолок "
        "размера заданы конфигом)."
    ),
)
async def upload_media(
    request: Request,
    file: UploadFile = File(...),
    kind: str = Form("image"),
    acc: UserModel = Depends(get_current_acc),
    storage: StorageSvc = Depends(get_storage_svc),
    mngr: SystemMediaMngr = Depends(get_media_mngr),
) -> Media:
    cfg: AppConfig = request.app.state.settings

    if kind not in _FOLDER_BY_KIND:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "недопустимый вид медиа")

    # Читаем с ограничением: на байт больше потолка — отказ (без OOM).
    data = await file.read(cfg.MEDIA_MAX_BYTES + 1)
    size = len(data)
    if size > cfg.MEDIA_MAX_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "файл слишком большой"
        )
    if size == 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "пустой файл")

    # Право зависит от размера.
    needed = _PERM_SMALL if size <= cfg.MEDIA_SMALL_MAX_BYTES else _PERM_LARGE
    perms = acc.role.perms if acc.role else None
    if not has_perm(perms, needed):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail=f"недостаточно прав: {needed}"
        )

    url = await storage.save(
        _FOLDER_BY_KIND[kind],
        file.filename or "upload",
        data,
        content_type=file.content_type,
    )
    media = await mngr.create(
        kind,
        url,
        backend=storage.backend,
        mime=file.content_type,
        size=size,
        owner_id=acc.id,
    )
    await mngr.s.commit()
    return Media.from_model(media)


__all__ = ["router"]
