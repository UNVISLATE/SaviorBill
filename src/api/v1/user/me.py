"""Профиль текущего пользователя (/api/v1/user/me)."""

from __future__ import annotations

import valkey.asyncio as valkey
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.auth import UserMngr, get_acc_mngr, get_current_acc
from dependencies.db import get_db_session
from dependencies.media import get_media_mngr
from dependencies.password import METHOD_DISABLED, resolve_reset_method
from dependencies.rbac import require_perm
from dependencies.settings import SystemSettingsMngr, get_settings_mngr
from dependencies.valkey import get_valkey_client
from enums import BaseRole
from models.service_attachment import ServiceAttachmentModel
from models.system_media import SystemMediaModel, SystemMediaMngr, all_storage_keys
from models.user import UserModel
from models.user_oauth import UserOauthMngr
from schemas.auth import Account, AvatarSet, MePatch, PasswordChange
from utils.config import AppConfig
from utils.mediabus import MediaBus
from utils.sec.pwd import hash_pass, verify_pass

router = APIRouter()


async def _account_response(acc: UserModel, session: AsyncSession) -> Account:
    """Собрать полный ответ профиля (с slugs привязанных OAuth-провайдеров)."""
    conns = await UserOauthMngr(session).list_for_account(acc.id)
    return Account.from_account(acc, oauth_providers=[c.provider for c in conns])


def _email_confirmed_by_oauth(
    email: str | None, oauth_emails: list[str | None]
) -> bool:
    """Подтверждён ли ``email`` какой-либо уже привязанной OAuth-учёткой.

    Сравнение регистронезависимое (email по стандарту принято сравнивать без
    учёта регистра домена/локальной части на практике большинства провайдеров).

    :arg email: новый email, который пытаются установить.
    :arg oauth_emails: email'ы, вернувшиеся от привязанных OAuth-провайдеров.
    :return: ``True``, если хотя бы одна привязка подтверждает этот email.
    """
    if not email:
        return False
    return any(e and e.lower() == email.lower() for e in oauth_emails)


@router.get(
    "/me",
    response_model=Account,
    summary="Current user profile",
    dependencies=[Depends(require_perm("user.profile.read"))],
)
async def me(
    acc: UserModel = Depends(get_current_acc),
    session: AsyncSession = Depends(get_db_session),
) -> Account:
    """Вернуть данные текущего аккаунта по access-токену."""
    return await _account_response(acc, session)


@router.patch(
    "/me",
    response_model=Account,
    summary="Update own login/email",
    description=(
        "Partial update, only send changed fields. Changing `email` to a "
        "value not confirmed by any linked OAuth account resets verification."
    ),
    dependencies=[Depends(require_perm("user.profile.edit"))],
)
async def patch_me(
    body: MePatch,
    acc: UserModel = Depends(get_current_acc),
    mngr: UserMngr = Depends(get_acc_mngr),
) -> Account:
    data = body.model_dump(exclude_unset=True)
    oauth_mngr = UserOauthMngr(mngr.s)

    if "login" in data and data["login"] != acc.login:
        clash = await mngr.by_login(data["login"])
        if clash is not None and clash.id != acc.id:
            raise HTTPException(status.HTTP_409_CONFLICT, "login already taken")
        acc.login = data["login"]

    if "email" in data and data["email"] != acc.email:
        new_email = data["email"]
        if new_email:
            clash = await mngr.by_email(new_email)
            if clash is not None and clash.id != acc.id:
                raise HTTPException(status.HTTP_409_CONFLICT, "email already taken")
        conns = await oauth_mngr.list_for_account(acc.id)
        confirmed = _email_confirmed_by_oauth(new_email, [c.email for c in conns])
        acc.email = new_email
        if not confirmed:
            # Новый email никем не подтверждён — аккаунт снова неверифицирован.
            await mngr.set_role_key(acc, BaseRole.GUEST)

    await mngr.s.commit()
    return await _account_response(acc, mngr.s)


@router.post(
    "/me/password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Change password",
    description=(
        "Requires `current_password` if a password is already set; not "
        "needed for an OAuth-only account setting a password for the first "
        "time. Blocked if `password.reset.method` is set to `disabled`."
    ),
    dependencies=[Depends(require_perm("user.profile.edit"))],
)
async def change_password(
    body: PasswordChange,
    acc: UserModel = Depends(get_current_acc),
    mngr: UserMngr = Depends(get_acc_mngr),
    settings: SystemSettingsMngr = Depends(get_settings_mngr),
) -> None:
    if await resolve_reset_method(settings) == METHOD_DISABLED:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "password change is disabled")
    if acc.has_pass:
        if not body.current_password or not verify_pass(
            acc.pass_hash, body.current_password
        ):
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED, "invalid current password"
            )
    acc.pass_hash = hash_pass(body.new_password)
    await mngr.s.commit()


async def _is_media_still_used(
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


async def _release_old_avatar(
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
    if await _is_media_still_used(
        media.s, old.id, exclude_account_id=exclude_account_id
    ):
        return
    cfg: AppConfig = request.app.state.settings
    bus = MediaBus(vk, cfg.MEDIA_TASK_STREAM, cfg.MEDIA_TASK_STREAM_MAXLEN)
    await bus.enqueue_delete(old.backend, all_storage_keys(old))
    await media.delete(old)


@router.put(
    "/me/avatar",
    response_model=Account,
    summary="Set or clear avatar",
    description=(
        "Sets avatar by `media_id` of an already uploaded media (see "
        "mediaworker); the media must belong to the current account. "
        "`media_id: null` removes the avatar. The previous avatar file is "
        "deleted if no longer referenced elsewhere."
    ),
    dependencies=[Depends(require_perm("user.profile.edit"))],
)
async def set_avatar(
    request: Request,
    body: AvatarSet,
    acc: UserModel = Depends(get_current_acc),
    mngr: UserMngr = Depends(get_acc_mngr),
    media: SystemMediaMngr = Depends(get_media_mngr),
    vk: valkey.Valkey = Depends(get_valkey_client),
) -> Account:
    if body.media_id is not None:
        m = await media.by_id(body.media_id)
        # Same 404 for "not found" and "belongs to another account" — a
        # distinct 403 would let callers enumerate existing media ids.
        if m is None or (m.owner_id is not None and m.owner_id != acc.id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "media not found")

    old_media_id = acc.avatar_media_id
    acc.avatar_media_id = body.media_id
    await mngr.s.commit()
    await mngr.s.refresh(acc)

    if old_media_id is not None and old_media_id != body.media_id:
        old = await media.by_id(old_media_id)
        if old is not None:
            await _release_old_avatar(
                request, vk, media, old, exclude_account_id=acc.id
            )
        await mngr.s.commit()

    return await _account_response(acc, mngr.s)


__all__ = ["router"]
