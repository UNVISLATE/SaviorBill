"""Доменные события email-рассылок."""

from __future__ import annotations


class EmailEvent:
    """Слаги шаблонов прямых писем (верификация, сброс пароля)."""

    EMAIL_VERIFY = "email.verify"  # запрошено подтверждение email
    PASSWORD_RESET = "password.reset"  # запрошен сброс пароля


__all__ = ["EmailEvent"]
