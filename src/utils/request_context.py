"""Контекст входящего запроса (Ray ID / Correlation ID)."""

from __future__ import annotations

import contextvars
import uuid

current_ray_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_ray_id", default=None
)


def generate_ray_id() -> str:
    """Генерация уникального ray_id для связывания логов, аудита и трейсинга."""
    return f"sb_ray_{uuid.uuid4().hex[:12]}"


def get_current_ray_id() -> str:
    """Получить текущий ray_id или сгенерировать fallback."""
    rid = current_ray_id_ctx.get()
    return rid or generate_ray_id()


__all__ = ["current_ray_id_ctx", "generate_ray_id", "get_current_ray_id"]
