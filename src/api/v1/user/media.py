"""Собственные загрузки медиа текущего пользователя (/api/v1/user/media)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from dependencies.auth import get_current_acc
from dependencies.media import get_media_mngr
from dependencies.rbac import require_perm
from models.system_media import SystemMediaMngr
from models.user import UserModel
from schemas.media import Media
from schemas.page import Page
from utils.pagination import PageParams, page_params, paginate

router = APIRouter()


@router.get(
    "/media",
    response_model=Page[Media],
    summary="My uploaded media",
    description=(
        "Own uploads (any status: processing/ready/error), newest first. "
        "Counts toward user.media.limit — see docs/media.md."
    ),
    dependencies=[Depends(require_perm("user.media.read"))],
)
async def my_media(
    pp: PageParams = Depends(page_params),
    acc: UserModel = Depends(get_current_acc),
    mngr: SystemMediaMngr = Depends(get_media_mngr),
) -> Page[Media]:
    items, total, has_more = await paginate(
        mngr.s,
        mngr.stmt_for_owner(acc.id),
        Media.from_model,
        limit=pp.limit,
        offset=pp.offset,
    )
    return Page(
        items=items, total=total, limit=pp.limit, offset=pp.offset, has_more=has_more
    )


__all__ = ["router"]
