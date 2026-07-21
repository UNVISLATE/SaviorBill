"""``/api/ws`` — WebSocket-роуты billing.

Живут в отдельном пакете ``apiws/`` (код организован отдельно от HTTP-роутов
в ``api/``), но URL — под общим ``/api`` (см. IMPLEMENTATION_PLAN.md §2/§7):
единый префикс для dev-прокси и продакшен-балансировщика, отдельное правило
под "/apiws" не нужно."""

from fastapi import APIRouter

from .v1 import router as v1_router

apiws_router = APIRouter(prefix="/api/ws")
apiws_router.include_router(v1_router)

__all__ = ["apiws_router"]
