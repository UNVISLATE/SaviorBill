"""Мягкая деградация при недоступности Valkey."""

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
