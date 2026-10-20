"""Доменные события, порождающие триггеры."""

from __future__ import annotations


class TriggerEvent:
    """Каталог событий-условий для триггеров."""

    USER_REGISTERED = "user.registered"  # зарегистрирован пользователь
    USER_VERIFIED = "user.verified"  # пользователь подтвердил email
    ORDER_CREATED = "order.created"  # оформлена покупка товара
    PAYMENT_PAID = "payment.paid"  # произведена оплата
    PAYMENT_REFUNDED = "payment.refunded"  # платёж возвращён (полностью)
    SERVICE_DELIVERED = "service.delivered"  # товар/услуга выданы
    SERVICE_KEYS_LOW = "service.keys.low"  # остаток ключей опустился ниже порога
    SERVICE_KEYS_EMPTY = "service.keys.empty"  # цифровые ключи для услуги закончились
    PAYMENT_CANCELLED = "payment.cancelled"  # платёж отменён
    PAYMENT_FAILED = "payment.failed"  # ошибка/сбой проведения платежа


ALL_EVENTS = [
    TriggerEvent.USER_REGISTERED,
    TriggerEvent.USER_VERIFIED,
    TriggerEvent.ORDER_CREATED,
    TriggerEvent.PAYMENT_PAID,
    TriggerEvent.PAYMENT_REFUNDED,
    TriggerEvent.SERVICE_DELIVERED,
    TriggerEvent.SERVICE_KEYS_LOW,
    TriggerEvent.SERVICE_KEYS_EMPTY,
    TriggerEvent.PAYMENT_CANCELLED,
    TriggerEvent.PAYMENT_FAILED,
]


__all__ = ["TriggerEvent", "ALL_EVENTS"]
