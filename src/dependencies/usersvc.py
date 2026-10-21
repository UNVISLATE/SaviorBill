"""DI для выдачи услуг пользователю."""

from __future__ import annotations

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.db import get_db_session
from dependencies.sec import make_secbox
from dependencies.triggers import get_dispatcher
from lifecycle.triggers import TriggerDispatcher
from lua.bus import LuaBus
from lua.deps import get_lua_bus_configured
from models.user_services import UserServicesMngr


async def get_usersvc_mngr(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    bus: LuaBus = Depends(get_lua_bus_configured),
    dispatcher: TriggerDispatcher = Depends(get_dispatcher),
) -> UserServicesMngr:
    cfg = request.app.state.settings
    return UserServicesMngr(session, bus, make_secbox(cfg), dispatcher=dispatcher)


__all__ = ["UserServicesMngr", "get_usersvc_mngr"]
