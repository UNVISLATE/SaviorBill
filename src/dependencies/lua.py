"""DI для шины LuaWorker."""

from __future__ import annotations

from fastapi import Request

from utils.config import AppConfig
from utils.luabus import LuaBus


def get_lua_bus(request: Request) -> LuaBus:
    """Собрать `LuaBus` из ресурсов приложения."""
    cfg: AppConfig = request.app.state.settings
    return LuaBus(
        request.app.state.valkey,
        cfg.LUA_TASK_STREAM,
        cfg.LUA_RESP_STREAM,
        cfg.LUA_CALL_TIMEOUT,
    )


__all__ = ["get_lua_bus"]
