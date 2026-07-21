"""WS-роуты mediaworker (realtime, отдельно от REST в ``api/``).

Структура зеркалит billing (``src/apiws/v1``) — так проще держать в голове,
где искать WS-роут по домену. URL при этом не разделяется: и REST, и WS
mediaworker живут под одним ``/api/media/*`` (см. IMPLEMENTATION_PLAN.md §2 —
единый префикс для dev-прокси, ``ws: true`` включается для всего ``/api/media``
сразу, роуты внутри не нужно перечислять отдельно).
"""

from fastapi import APIRouter

from .v1 import router as v1_router

router = APIRouter()
router.include_router(v1_router)

__all__ = ["router"]
