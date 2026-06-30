"""Отправка email через SMTP (настройки берутся из таблицы settings)."""

from __future__ import annotations

from email.message import EmailMessage

import aiosmtplib


class MailSvc:
    """Тонкий сервис отправки писем по SMTP-настройкам из БД."""

    def __init__(
        self,
        host: str | None,
        port: int,
        user: str | None,
        password: str | None,
        sender: str | None,
        use_tls: bool,
    ) -> None:
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.sender = sender or user
        self.use_tls = use_tls

    @property
    def configured(self) -> bool:
        """Готов ли сервис к отправке (есть хост и отправитель)."""
        return bool(self.host and self.sender)

    async def send(
        self, to: str, subject: str, body: str, *, is_html: bool = False
    ) -> None:
        """Отправить письмо (текст или HTML)."""
        if not self.configured:
            raise RuntimeError("SMTP не настроен")

        msg = EmailMessage()
        msg["From"] = self.sender
        msg["To"] = to
        msg["Subject"] = subject
        if is_html:
            msg.set_content("Для просмотра письма используйте HTML-совместимый клиент.")
            msg.add_alternative(body, subtype="html")
        else:
            msg.set_content(body)

        # STARTTLS на 587, неявный TLS на 465.
        await aiosmtplib.send(
            msg,
            hostname=self.host,
            port=self.port,
            username=self.user or None,
            password=self.password or None,
            start_tls=self.use_tls and self.port != 465,
            use_tls=self.port == 465,
        )


__all__ = ["MailSvc"]
