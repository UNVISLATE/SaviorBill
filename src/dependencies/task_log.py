"""DI для журнала фактов о тасках (lua/media) — см. utils/task_log.py."""

from __future__ import annotations

from fastapi import Request

from telemetry.task_log import TaskLog


def get_task_log(request: Request) -> TaskLog:
    """Синглтон ``TaskLog``, созданный в lifespan (``app.state.task_log``)."""
    return request.app.state.task_log


__all__ = ["get_task_log"]
