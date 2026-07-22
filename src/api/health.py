from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request, Response
from sqlalchemy import text

from core.config import AppConfig, APP_NAME, APP_VERSION
from schemas.system import HealthCheck

router = APIRouter(tags=["health"])

_READY_TIMEOUT_SEC = 2.0


@router.get("/health")
async def health(request: Request):
    """Liveness — процесс жив и отвечает, без проверки зависимостей."""
    settings: AppConfig = request.app.state.settings
    return HealthCheck(
        status="ok",
        app_name=APP_NAME,
        app_version=APP_VERSION,
    )


@router.get("/health/ready")
async def ready(request: Request, response: Response) -> dict:
    """Readiness — доступны ли Postgres и Valkey (с коротким таймаутом).

    Отдаёт 503, если зависимость недоступна — используется
    оркестратором/балансировщиком, чтобы не слать трафик на инстанс,
    который жив, но потерял связь с БД или Valkey.
    """
    checks: dict[str, str] = {}
    ok = True

    async def _check_db() -> None:
        async with request.app.state.db_sessionmaker() as session:
            await session.execute(text("SELECT 1"))

    try:
        await asyncio.wait_for(_check_db(), timeout=_READY_TIMEOUT_SEC)
        checks["db"] = "ok"
    except Exception:  # noqa: BLE001 — любая ошибка здесь = "не готов"
        checks["db"] = "unavailable"
        ok = False

    try:
        await asyncio.wait_for(
            request.app.state.valkey.ping(), timeout=_READY_TIMEOUT_SEC
        )
        checks["valkey"] = "ok"
    except Exception:  # noqa: BLE001
        checks["valkey"] = "unavailable"
        ok = False

    # Информационно, не влияет на общий readiness (billing по-прежнему готов
    # обслуживать HTTP без живых lua-воркеров) — сколько реплик LuaWorker
    # прислали живой heartbeat (см. telemetry/instance_metrics.py).
    try:
        settings: AppConfig = request.app.state.settings
        cursor, keys = await asyncio.wait_for(
            request.app.state.valkey.scan(
                0, match=f"{settings.LUA_METRICS_PREFIX}*", count=100
            ),
            timeout=_READY_TIMEOUT_SEC,
        )
        checks["lua_workers"] = f"{len(keys)} active"
    except Exception:  # noqa: BLE001 — не критично для readiness
        checks["lua_workers"] = "unknown"

    response.status_code = 200 if ok else 503
    return {"status": "ok" if ok else "unavailable", "checks": checks}
