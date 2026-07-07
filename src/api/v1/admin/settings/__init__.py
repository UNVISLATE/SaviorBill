"""Админ: настройки системы (/api/v1/admin/settings).

Модуль объединяет:
- ``ratelimits`` — управление лимитами частоты запросов (Valkey-оверрайды);
- ``raw`` — ручное (raw) управление строками таблицы ``settings``.
"""

from __future__ import annotations

from fastapi import APIRouter

from .ratelimits import router as ratelimits_router
from .raw import router as raw_router

router = APIRouter()
router.include_router(ratelimits_router)
router.include_router(raw_router)

__all__ = ["router"]
