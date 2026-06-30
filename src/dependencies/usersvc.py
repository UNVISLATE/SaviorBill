"""DI для выдачи услуг пользователю."""

from __future__ import annotations

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.db import get_db_session
from dependencies.lua import get_lua_bus
from models.user_services import UserServicesMngr


def get_usersvc_mngr(
    request: Request, session: AsyncSession = Depends(get_db_session)
) -> UserServicesMngr:
    return UserServicesMngr(session, get_lua_bus(request))


__all__ = ["UserServicesMngr", "get_usersvc_mngr"]
