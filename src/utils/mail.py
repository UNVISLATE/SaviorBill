"""Отправка email через SMTP (настройки берутся из таблицы settings)."""

from __future__ import annotations

import asyncio
import re
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

        # Защита от Header Injection (CRLF)
        clean_subject = re.sub(r"[\r\n\0]+", " ", str(subject or "")).strip()
        clean_name = re.sub(r"[\r\n\0]+", " ", str(effective_name or "")).strip() if effective_name else None
        clean_sender = re.sub(r"[\r\n\0]+", "", str(effective_sender or "")).strip()
        clean_to = re.sub(r"[\r\n\0]+", "", str(to or "")).strip()

        msg = EmailMessage()
        if clean_name:
            msg["From"] = formataddr((clean_name, clean_sender))
        else:
            msg["From"] = clean_sender

        msg["To"] = clean_to
        msg["Subject"] = clean_subject
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


class LuaMailSvc:
    """Транспорт отправки писем через Lua-скрипт (API провайдера: smtp.bz, Resend, Brevo и т.д.)."""

    def __init__(
        self,
        bus,  # LuaBus | None
        session,  # AsyncSession
        script_id: int | None,
        script_version: str | None = None,
        sender: str | None = None,
        from_name: str | None = None,
        config: dict | None = None,
    ) -> None:
        self.bus = bus
        self.s = session
        self.script_id = script_id
        self.script_version = script_version
        self.sender = sender
        self.from_name = from_name
        self.config = config or {}

    @property
    def configured(self) -> bool:
        """Готов ли Lua-транспорт к отправке."""
        return bool(self.bus and self.script_id)

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
        """Отправить письмо через Lua-скрипт почтового транспорта."""
        if not self.configured:
            raise RuntimeError("Lua-транспорт почты не настроен (не указан скрипт или шина LuaWorker)")

        from models.system_scripts import SystemScriptsModel, resolve_version
        from lua.context import LuaRunner

        effective_sender = sender_override or self.sender
        effective_name = from_name_override if from_name_override is not None else self.from_name

        script = await self.s.get(SystemScriptsModel, int(self.script_id))
        if script is None or not script.is_active:
            raise RuntimeError(f"Lua-скрипт почтового транспорта #{self.script_id} не найден или неактивен")

        filename, resolved_version = await resolve_version(self.s, script, self.script_version)

        # Очистка заголовков от CRLF
        clean_subject = re.sub(r"[\r\n\0]+", " ", str(subject or "")).strip()
        clean_name = re.sub(r"[\r\n\0]+", " ", str(effective_name or "")).strip() if effective_name else None
        clean_sender = re.sub(r"[\r\n\0]+", "", str(effective_sender or "")).strip()
        clean_to = re.sub(r"[\r\n\0]+", "", str(to or "")).strip()

        email_data = {
            "to": clean_to,
            "subject": clean_subject,
            "body": body,
            "is_html": is_html,
            "from_email": clean_sender,
            "from_name": clean_name,
        }

        runner = LuaRunner(self.bus)
        res = await runner.run_email(
            script,
            "send",
            email_data,
            config=self.config,
            filename=filename,
            version=resolved_version,
            requested_version=self.script_version,
        )

        if isinstance(res, dict) and res.get("ok") is False:
            err = res.get("error") or "Unknown error from Lua email script"
            raise RuntimeError(f"Lua email transport failed: {err}")


__all__ = ["MailSvc", "LuaMailSvc"]
