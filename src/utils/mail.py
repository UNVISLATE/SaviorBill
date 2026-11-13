"""Отправка email через SMTP (настройки берутся из таблицы settings)."""

from __future__ import annotations

import asyncio
from email.message import EmailMessage
from email.utils import formataddr

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
        encryption: str = "starttls",
        use_tls: bool | None = None,
        from_name: str | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.sender = sender or user
        self.from_name = from_name
        self.timeout = float(timeout or 10.0)

        # Обратная совместимость с use_tls: bool
        if use_tls is not None and encryption == "starttls":
            if not use_tls:
                self.encryption = "none"
            elif port in (465, 9465, 8465):
                self.encryption = "ssl"
            else:
                self.encryption = "starttls"
        else:
            norm_enc = str(encryption or "starttls").lower().strip()
            if norm_enc in ("ssl", "tls", "direct_tls", "implicit"):
                self.encryption = "ssl"
            elif norm_enc in ("none", "plain", "false", "0"):
                self.encryption = "none"
            else:
                self.encryption = "starttls"

    @property
    def use_tls(self) -> bool:
        """Обратная совместимость: включено ли шифрование."""
        return self.encryption != "none"

    @property
    def configured(self) -> bool:
        """Готов ли сервис к отправке (есть хост и отправитель)."""
        return bool(self.host and self.sender)

    async def send(
        self,
        to: str,
        subject: str,
        body: str,
        *,
        is_html: bool = False,
        sender_override: str | None = None,
        from_name_override: str | None = None,
    ) -> None:
        """Отправить письмо (текст или HTML).

        Поддерживает произвольные порты и независимый режим шифрования:
        - ssl: прямое TLS/SSL подключение с первого байта (use_tls=True)
        - starttls: подключение и апгрейд через команду STARTTLS (start_tls=True)
        - none: открытое текстовое подключение (use_tls=False, start_tls=False)
        """
        if not self.configured and not sender_override:
            raise RuntimeError("SMTP не настроен")

        effective_sender = sender_override or self.sender
        effective_name = from_name_override if from_name_override is not None else self.from_name

        msg = EmailMessage()
        if effective_name:
            msg["From"] = formataddr((effective_name, effective_sender))
        else:
            msg["From"] = effective_sender

        msg["To"] = to
        msg["Subject"] = subject
        if is_html:
            msg.set_content("Для просмотра письма используйте HTML-совместимый клиент.")
            msg.add_alternative(body, subtype="html")
        else:
            msg.set_content(body)

        is_ssl = self.encryption == "ssl"
        is_starttls = self.encryption == "starttls"

        await aiosmtplib.send(
            msg,
            hostname=self.host,
            port=self.port,
            username=self.user or None,
            password=self.password or None,
            use_tls=is_ssl,
            start_tls=is_starttls,
            timeout=self.timeout,
        )


__all__ = ["MailSvc"]
