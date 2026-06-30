"""Действие триггера: отправка письма по шаблону."""

from __future__ import annotations

from integrations.email import EmailSender
from models.email_templates import EmailMngr

from .base import BaseAction, dig


class EmailAction(BaseAction):
    """Рендерит шаблон (``config.template_id``) и шлёт на ``config.to_field``."""

    key = "email"

    def __init__(self, sender: EmailSender, templates: EmailMngr) -> None:
        self.sender = sender
        self.templates = templates

    async def run(self, ctx: dict, config: dict) -> bool:
        """Отправить письмо адресату из контекста.

        :arg ctx: контекст события.
        :arg config: ``{template_id, to_field}``.
        :return: ``True`` если письмо отправлено.
        """
        if not self.sender.configured:
            return False

        template_id = config.get("template_id")
        to = dig(ctx, config.get("to_field") or "user.email")
        if not template_id or not to:
            return False

        tpl = await self.templates.by_id(int(template_id))
        if tpl is None or not tpl.is_active:
            return False

        await self.sender.send_by_template(tpl, str(to), ctx)
        return True


__all__ = ["EmailAction"]
