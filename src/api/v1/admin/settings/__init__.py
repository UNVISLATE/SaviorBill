"""Админ: настройки системы (/api/v1/admin/settings).

Модуль объединяет:
- ``ratelimits`` — управление лимитами частоты запросов (Valkey-оверрайды);
- ``raw`` — ручное (raw) управление строками таблицы ``settings``;
- ``ui`` — эргономичная запись ``ui.*`` (брендинг админки/клиента) поверх той
  же таблицы (JSON/form тело вместо ручного JSON-квотирования в ``raw``);
- ``secrets`` — ротация ключа шифрования (перешифровка секретных колонок).
"""

from __future__ import annotations

from fastapi import APIRouter

from .ratelimits import router as ratelimits_router
from .raw import router as raw_router
from .secrets import router as secrets_router
from .ui import router as ui_router

router = APIRouter()
router.include_router(ratelimits_router, prefix="/ratelimits")
router.include_router(raw_router, prefix="/raw")
router.include_router(secrets_router, prefix="/secrets")
router.include_router(ui_router, prefix="/ui")

__all__ = ["router"]
