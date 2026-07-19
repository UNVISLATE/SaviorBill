"""Рендеринг email-шаблонов на jinja2."""

from __future__ import annotations

from jinja2 import StrictUndefined
from jinja2.sandbox import SandboxedEnvironment


class MailRenderer:
    """Безопасный рендер темы и тела письма из строковых шаблонов."""

    def __init__(self) -> None:
        self._html = SandboxedEnvironment(
            autoescape=True, undefined=StrictUndefined, enable_async=False
        )
        self._text = SandboxedEnvironment(
            autoescape=False, undefined=StrictUndefined, enable_async=False
        )

    def subject(self, template: str, ctx: dict) -> str:
        """Отрендерить тему (всегда как текст, без HTML-экранирования)."""
        return self._text.from_string(template).render(**ctx).strip()

    def body(self, template: str, ctx: dict, *, is_html: bool) -> str:
        """Отрендерить тело письма (HTML или текст)."""
        env = self._html if is_html else self._text
        return env.from_string(template).render(**ctx)


__all__ = ["MailRenderer"]
