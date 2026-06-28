"""Первичная инициализация системы при старте.

Идемпотентно создаёт роль ``owner`` (все права) и owner-пользователя из
``OWNER_*`` переменных окружения, а также сеет SMTP-настройки в таблицу
``settings``. Безопасно вызывать на каждом запуске.
"""

from __future__ import annotations

import valkey.asyncio as valkey
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dependencies.settings import SettingsMngr
from models.roles import Role
from models.user import Account
from utils.config import AppConfig
from utils.sec.box import SecBox
from utils.sec.pwd import hash_pass

OWNER_ROLE = "owner"


async def _ensure_owner_role(session: AsyncSession) -> Role:
    """Создать (если нет) системную роль owner со всеми правами."""
    role = await session.scalar(select(Role).where(Role.name == OWNER_ROLE))
    if role is None:
        role = Role(
            name=OWNER_ROLE,
            title="Владелец",
            is_system=True,
            perms={"*": True},
        )
        session.add(role)
        await session.flush()
    return role


async def _ensure_owner_user(session: AsyncSession, cfg: AppConfig, role: Role) -> None:
    """Создать owner-пользователя при первом запуске (если его ещё нет)."""
    if not cfg.OWNER_LOGIN or not cfg.OWNER_PASS:
        return
    existing = await session.scalar(
        select(Account).where(Account.login == cfg.OWNER_LOGIN)
    )
    if existing is not None:
        return
    session.add(
        Account(
            login=cfg.OWNER_LOGIN,
            email=cfg.OWNER_EMAIL,
            pass_hash=hash_pass(cfg.OWNER_PASS),
            is_active=True,
            is_verified=True,
            role_id=role.id,
        )
    )
    await session.flush()


async def bootstrap(
    cfg: AppConfig,
    sessionmaker: async_sessionmaker[AsyncSession],
    vk: valkey.Valkey,
) -> None:
    """Выполнить первичную инициализацию в одной транзакции."""
    async with sessionmaker() as session:
        role = await _ensure_owner_role(session)
        await _ensure_owner_user(session, cfg, role)
        settings = SettingsMngr(session, vk, SecBox(cfg.SECRETS_KEY))
        await settings.seed_smtp(cfg)
        await session.commit()


__all__ = ["bootstrap"]
