"""DI для шины LuaWorker."""

from __future__ import annotations

from fastapi import Depends, Request

from dependencies.settings import SystemSettingsMngr, get_settings_mngr
from dependencies.task_log import get_task_log
from utils.config import AppConfig
from utils.luabus import LuaBus
from observability.task_log import TaskLog


def get_lua_bus(request: Request) -> LuaBus:
    """Собрать `LuaBus` из ENV-конфигурации (без ретраев, без runtime-переопределений).

    Используется там, где нет доступа к `SystemSettingsMngr` (сессии БД) —
    например, фоновый `BillingLoop`. Для request-scoped вызовов предпочтителен
    :func:`get_lua_bus_configured` — таймаут/ретраи настраиваются в рантайме.
    """
    cfg: AppConfig = request.app.state.settings
    return LuaBus(
        request.app.state.valkey,
        cfg.LUA_TASK_STREAM,
        cfg.LUA_RESP_STREAM,
        cfg.LUA_CALL_TIMEOUT,
        task_stream_maxlen=cfg.LUA_TASK_STREAM_MAXLEN,
        task_log=request.app.state.task_log,
    )


async def get_lua_bus_configured(
    request: Request,
    settings: SystemSettingsMngr = Depends(get_settings_mngr),
    task_log: TaskLog = Depends(get_task_log),
) -> LuaBus:
    """`LuaBus` с runtime-настройками таймаута/ретраев (`SystemSettingsMngr`).

    Настройки читаются через кэш Valkey (см. `SystemSettingsMngr`), поэтому
    не бьём в БД на каждый вызов. ENV (`cfg.LUA_CALL_TIMEOUT`) остаётся
    дефолтом, пока настройка не задана в БД — обычный паттерн проекта (см.
    `settings_def.py`).
    """
    cfg: AppConfig = request.app.state.settings
    timeout = await settings.get_int("lua.call_timeout_sec", cfg.LUA_CALL_TIMEOUT)
    max_retries = await settings.get_int("lua.max_retries", 2)
    backoff = await settings.get_int("lua.retry_backoff_sec", 5)
    return LuaBus(
        request.app.state.valkey,
        cfg.LUA_TASK_STREAM,
        cfg.LUA_RESP_STREAM,
        default_timeout=timeout or cfg.LUA_CALL_TIMEOUT,
        max_retries=max_retries or 0,
        retry_backoff=backoff or 0,
        task_stream_maxlen=cfg.LUA_TASK_STREAM_MAXLEN,
        task_log=task_log,
    )


__all__ = ["get_lua_bus", "get_lua_bus_configured"]
