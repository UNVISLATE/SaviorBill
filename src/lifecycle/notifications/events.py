"""Доменные события email-рассылок."""

from __future__ import annotations


class EmailEvent:
    """Слаги шаблонов прямых писем (верификация, сброс пароля, клейм)."""

    EMAIL_VERIFY = "email.verify"  # запрошено подтверждение email
    PASSWORD_RESET = "password.reset"  # запрошен сброс пароля
    OAUTH_LINK_CONFIRM = "oauth.link_confirm"  # подтверждение привязки OAuth к существующему email
    GUEST_CLAIM_CONFIRM = "guest.claim_confirm"  # подтверждение владения гостевым аккаунтом
    GUEST_ORDER_CREATED = "guest.order_created"  # уведомление о гостевом заказе


__all__ = ["EmailEvent"]
