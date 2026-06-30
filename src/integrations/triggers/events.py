"""Доменные события, порождающие триггеры."""

from __future__ import annotations


class TriggerEvent:
    """Каталог событий-условий для триггеров."""

    USER_REGISTERED = "user.registered"  # зарегистрирован пользователь
    USER_VERIFIED = "user.verified"  # пользователь подтвердил email
    ORDER_CREATED = "order.created"  # оформлена покупка товара
    PAYMENT_PAID = "payment.paid"  # произведена оплата
    SERVICE_DELIVERED = "service.delivered"  # товар/услуга выданы


ALL_EVENTS = [
    TriggerEvent.USER_REGISTERED,
    TriggerEvent.USER_VERIFIED,
    TriggerEvent.ORDER_CREATED,
    TriggerEvent.PAYMENT_PAID,
    TriggerEvent.SERVICE_DELIVERED,
]


__all__ = ["TriggerEvent", "ALL_EVENTS"]
