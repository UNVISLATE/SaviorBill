from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request, Response

router = APIRouter()

_READY_TIMEOUT_SEC = 2.0


@router.get("/health")
async def health() -> dict:
    """Liveness — процесс жив и отвечает, без проверки зависимостей."""
    return {"status": "ok"}


@router.get("/health/ready")
async def ready(request: Request, response: Response) -> dict:
    """Readiness — доступны ли Postgres и Valkey (с коротким таймаутом).

    В отличие от ``/health`` этот роут может отдать 503 — используется
    оркестратором/балансировщиком, чтобы не слать трафик на воркер, который
    жив, но потерял связь с зависимостями (например, при рестарте БД).
    """
    checks: dict[str, str] = {}
    ok = True

    db = request.app.state.db
    try:
        await asyncio.wait_for(db.ping(), timeout=_READY_TIMEOUT_SEC)
        checks["db"] = "ok"
    except Exception:  # noqa: BLE001 — любая ошибка здесь = "не готов"
        checks["db"] = "unavailable"
        ok = False

    vk = request.app.state.vk
    try:
        await asyncio.wait_for(vk.ping(), timeout=_READY_TIMEOUT_SEC)
        checks["valkey"] = "ok"
    except Exception:  # noqa: BLE001
        checks["valkey"] = "unavailable"
        ok = False

    response.status_code = 200 if ok else 503
    return {"status": "ok" if ok else "unavailable", "checks": checks}


__all__ = ["router"]
