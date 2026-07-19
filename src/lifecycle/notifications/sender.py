"""Отправитель писем по шаблонам."""

from __future__ import annotations

from models.email_templates import EmailMngr
from utils.mail import MailSvc

from .renderer import MailRenderer


class EmailSender:
    """Рендер шаблона из БД и отправка письма получателю."""

    def __init__(
        self,
        mail: MailSvc,
        templates: EmailMngr,
        renderer: MailRenderer | None = None,
    ) -> None:
        self.mail = mail
        self.templates = templates
        self.renderer = renderer or MailRenderer()

    @property
    def configured(self) -> bool:
        """Готов ли транспорт к отправке."""
        return self.mail.configured

    async def send_template(self, slug: str, to: str, ctx: dict) -> bool:
        """Отправить письмо по слагу шаблона. Возвращает факт отправки.

        ``False`` — шаблон не найден/выключен или транспорт не настроен
        (отправка не критична для основной операции).
        """
        tpl = await self.templates.by_slug(slug)
        if tpl is None or not tpl.is_active or not self.configured:
            return False

        body_tpl = await self.templates.read_body(tpl)
        subject = self.renderer.subject(tpl.subject, ctx)
        body = self.renderer.body(body_tpl, ctx, is_html=tpl.is_html)
        await self.mail.send(to, subject, body, is_html=tpl.is_html)
        return True

    async def send_by_template(self, tpl, to: str, ctx: dict) -> None:
        """Отправить письмо по уже загруженному объекту шаблона."""
        body_tpl = await self.templates.read_body(tpl)
        subject = self.renderer.subject(tpl.subject, ctx)
        body = self.renderer.body(body_tpl, ctx, is_html=tpl.is_html)
        await self.mail.send(to, subject, body, is_html=tpl.is_html)


__all__ = ["EmailSender"]
