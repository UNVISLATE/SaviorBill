"""Доменные события, порождающие триггеры."""

from __future__ import annotations


class TriggerEvent:
    """Каталог событий-условий для триггеров."""

    USER_REGISTERED = "user.registered"  # зарегистрирован пользователь
    USER_VERIFIED = "user.verified"  # пользователь подтвердил email
    ORDER_CREATED = "order.created"  # оформлена покупка товара
    ORDER_FAILED = "order.failed"  # сбой/ошибка при выдаче заказа
    ORDER_CANCELLED = "order.cancelled"  # отмена заказа покупателем или администратором
    PAYMENT_PAID = "payment.paid"  # произведена оплата
    PAYMENT_REFUNDED = "payment.refunded"  # платёж возвращён (полностью)
    SERVICE_DELIVERED = "service.delivered"  # товар/услуга выданы
    SERVICE_KEYS_LOW = "service.keys.low"  # остаток ключей опустился ниже порога
    SERVICE_KEYS_EMPTY = "service.keys.empty"  # цифровые ключи для услуги закончились
    KEY_STOCK_LOW = "key.stock.low"  # остаток ключей в пуле ниже порогового N
    PAYMENT_CANCELLED = "payment.cancelled"  # платёж отменён
    PAYMENT_FAILED = "payment.failed"  # ошибка/сбой проведения платежа
    USER_BALANCE_CHANGED = "user.balance.changed"  # изменение баланса пользователя
    PROMOCODE_APPLIED = "promocode.applied"  # активация промокода при покупке


ALL_EVENTS = [
    TriggerEvent.USER_REGISTERED,
    TriggerEvent.USER_VERIFIED,
    TriggerEvent.ORDER_CREATED,
    TriggerEvent.ORDER_FAILED,
    TriggerEvent.ORDER_CANCELLED,
    TriggerEvent.PAYMENT_PAID,
    TriggerEvent.PAYMENT_REFUNDED,
    TriggerEvent.SERVICE_DELIVERED,
    TriggerEvent.SERVICE_KEYS_LOW,
    TriggerEvent.SERVICE_KEYS_EMPTY,
    TriggerEvent.KEY_STOCK_LOW,
    TriggerEvent.PAYMENT_CANCELLED,
    TriggerEvent.PAYMENT_FAILED,
    TriggerEvent.USER_BALANCE_CHANGED,
    TriggerEvent.PROMOCODE_APPLIED,
]


__all__ = ["TriggerEvent", "ALL_EVENTS"]
