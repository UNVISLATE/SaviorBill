"""Email как интеграция: шаблоны (jinja2) и отправка по событиям/шаблонам."""

from __future__ import annotations

from .events import EmailEvent
from .renderer import MailRenderer
from .sender import EmailSender

__all__ = ["EmailEvent", "MailRenderer", "EmailSender"]
