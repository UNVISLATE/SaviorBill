"""Создание пользователя-владельца при первом запуске."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.roles import Role
from models.user import UserModel
from utils.config import AppConfig
from security.sec.pwd import hash_pass

log = logging.getLogger("saviorbill.init")

Account = UserModel


async def create_owner(
    session: AsyncSession, cfg: AppConfig, owner_role: Role
) -> UserModel | None:
    """Создать owner-пользователя (если задан в ENV и ещё не существует)."""
    if not cfg.OWNER_LOGIN or not cfg.OWNER_PASS:
        log.info("owner user not created: OWNER_LOGIN or OWNER_PASS not set")
        return None

    existing = await session.scalar(
        select(UserModel).where(UserModel.login == cfg.OWNER_LOGIN)
    )
    if existing is not None:
        return existing

    acc = UserModel(
        login=cfg.OWNER_LOGIN,
        email=cfg.OWNER_EMAIL,
        pass_hash=hash_pass(cfg.OWNER_PASS),
        role_id=owner_role.id,
    )
    session.add(acc)
    await session.flush()
    acc.role = owner_role
    log.info("created owner-user %r", cfg.OWNER_LOGIN)
    return acc


__all__ = ["create_owner"]
