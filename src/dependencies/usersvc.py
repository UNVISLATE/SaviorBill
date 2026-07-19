"""DI для выдачи услуг пользователю."""

from __future__ import annotations

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.db import get_db_session
from lua.deps import get_lua_bus_configured
from dependencies.sec import make_secbox
from models.user_services import UserServicesMngr
from lua.bus import LuaBus


async def get_usersvc_mngr(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    bus: LuaBus = Depends(get_lua_bus_configured),
) -> UserServicesMngr:
    cfg = request.app.state.settings
    return UserServicesMngr(session, bus, make_secbox(cfg))


__all__ = ["UserServicesMngr", "get_usersvc_mngr"]
