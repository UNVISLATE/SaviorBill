"""Контекст входящего запроса (Trace ID / Correlation ID)."""

from __future__ import annotations

import contextvars
import secrets

current_trace_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_trace_id", default=None
)


def generate_trace_id() -> str:
    """Генерация стандартного 32-значного hex trace_id (W3C Trace Context)."""
    return secrets.token_hex(16)


def get_current_trace_id() -> str:
    """Получить текущий активный trace_id:

    1. Из спана OpenTelemetry (если включен).
    2. Из ContextVar текущего HTTP-запроса.
    3. Либо сгенерировать детерминированный fallback (32 hex).
    """
    try:
        from telemetry.otel import current_trace_id

        otel_id = current_trace_id()
        if otel_id:
            return otel_id
    except Exception:
        pass

    ctx_id = current_trace_id_ctx.get()
    return ctx_id or generate_trace_id()


__all__ = ["current_trace_id_ctx", "generate_trace_id", "get_current_trace_id"]
