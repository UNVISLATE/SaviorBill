"""Общие хелперы профиля аккаунта — используются и `user/me.py`
(самообслуживание), и `admin/users.py` (админ-действия над чужим профилем)."""

from __future__ import annotations

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
import valkey.asyncio as valkey

from core.config import AppConfig
from messaging.mediabus import MediaBus
from models.service_attachment import ServiceAttachmentModel
from models.system_media import SystemMediaModel, SystemMediaMngr, all_storage_keys
from models.user import UserModel
from models.user_oauth import UserOauthMngr
from schemas.auth import Account


async def account_response(acc: UserModel, session: AsyncSession) -> Account:
    """Собрать полный ответ профиля (с slugs привязанных OAuth-провайдеров)."""
    conns = await UserOauthMngr(session).list_for_account(acc.id)
    referred_by_login: str | None = None
    if acc.referred_by is not None:
        referred_by_login = await session.scalar(
            select(UserModel.login).where(UserModel.id == acc.referred_by)
        )
    referral_count = 0
    if acc.ref_code is not None:
        referral_count = (
            await session.scalar(
                select(func.count()).where(UserModel.referred_by == acc.id)
            )
            or 0
        )
    return Account.from_account(
        acc,
        oauth_providers=[c.provider for c in conns],
        referred_by_login=referred_by_login,
        referral_count=referral_count,
    )


async def is_media_still_used(
    session: AsyncSession, media_id: int, *, exclude_account_id: int
) -> bool:
    """Есть ли ещё ссылки на медиа, кроме аватарки указанного аккаунта."""
    other_avatar = await session.scalar(
        select(UserModel.id)
        .where(UserModel.avatar_media_id == media_id)
        .where(UserModel.id != exclude_account_id)
        .limit(1)
    )
    if other_avatar is not None:
        return True
    attachment = await session.scalar(
        select(ServiceAttachmentModel.id)
        .where(ServiceAttachmentModel.media_id == media_id)
        .limit(1)
    )
    return attachment is not None


async def release_old_avatar(
    request: Request,
    vk: valkey.Valkey,
    media: SystemMediaMngr,
    old: SystemMediaModel,
    *,
    exclude_account_id: int,
) -> None:
    """Удалить файл старой аватарки, если он больше нигде не используется.

    Файл удаляем только для медиа, загруженного самим пользователем
    (``owner_id == exclude_account_id``) — чужие/системные медиа не трогаем.
    """
    if old.owner_id != exclude_account_id:
        return
    if await is_media_still_used(media.s, old.id, exclude_account_id=exclude_account_id):
        return
    cfg: AppConfig = request.app.state.settings
    bus = MediaBus(
        vk, cfg.MEDIA_TASK_STREAM, cfg.MEDIA_TASK_STREAM_MAXLEN, signing_key=cfg.BUS_SIGNING_KEY
    )
    await bus.enqueue_delete(old.backend, all_storage_keys(old))
    await media.delete(old)


__all__ = ["account_response", "is_media_still_used", "release_old_avatar"]
