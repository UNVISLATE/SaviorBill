"""Мягкая деградация при недоступности Valkey.

Valkey — не источник истины для денег и прав, но на нём висят rate-limit,
анти-брутфорс и трекинг сессий. Раньше его падение возвращало 500 на логине,
покупках и OAuth, то есть полностью роняло платформу (см. AUDIT.md §2.3).

Здесь — единственное место, где решается, что при ошибке Valkey можно
продолжить работу. Использовать **только** для вспомогательных механизмов:
подписи, RBAC и любые денежные операции обязаны падать (fail-closed).
"""

from __future__ import annotations

import asyncio
import logging

from valkey.exceptions import ValkeyError

from telemetry.metrics import valkey_degraded_total

log = logging.getLogger("saviorbill.valkey")

#: Ошибки, которые считаем «Valkey сейчас недоступен».
VALKEY_ERRORS: tuple[type[BaseException], ...] = (
    ValkeyError,
    OSError,
    asyncio.TimeoutError,
)


def note_degraded(component: str, exc: BaseException) -> None:
    """Зафиксировать деградацию: метрика + warning."""
    valkey_degraded_total.labels(component=component).inc()
    log.warning("valkey unavailable, %s degraded: %s", component, exc)


__all__ = ["VALKEY_ERRORS", "note_degraded"]
