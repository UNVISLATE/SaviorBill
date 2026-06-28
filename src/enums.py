"""Доменные типы-константы (статусы, виды) для всего приложения.

Это не SQLAlchemy-модели, а простые наборы строковых констант. Держим их
отдельно от ``models`` (там — только таблицы) и не используем PG-enum, чтобы
миграции оставались простыми, а значения легко расширялись.
"""

from __future__ import annotations


class Delivery:
    """Способ доставки услуги."""

    KEY = "key"  # выдача готовым цифровым ключом из пула
    LUA = "lua"  # выдача через исполнение Lua-скрипта


class OrderStatus:
    """Жизненный цикл заказанной услуги."""

    INITIATED = "initiated"
    PROCESSING = "processing"
    DELIVERED = "delivered"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PayStatus:
    """Статус платежа (денежной транзакции через провайдера)."""

    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"


# Обратная совместимость: прежнее имя статуса пополнения.
TopupStatus = PayStatus


class PayTarget:
    """Назначение платежа: пополнить баланс или оплатить конкретную услугу."""

    BALANCE = "balance"
    SERVICE = "service"


class PromoKind:
    """Тип промокода."""

    BONUS = "bonus"  # пополнение бонусного баланса
    DISCOUNT = "discount"  # скидка на товар (применяется при заказе)
    SERVICE = "service"  # выдача услуги по промокоду


class DiscountType:
    """Как трактовать значение скидочного промокода."""

    PERCENT = "percent"
    FIXED = "fixed"


class ScriptKind:
    """Назначение Lua-скрипта."""

    SERVICE = "service"  # доставка услуги
    PAYMENT = "payment"  # платёжная интеграция
    GENERIC = "generic"  # прочее


__all__ = [
    "Delivery",
    "OrderStatus",
    "PayStatus",
    "TopupStatus",
    "PayTarget",
    "PromoKind",
    "DiscountType",
    "ScriptKind",
]
