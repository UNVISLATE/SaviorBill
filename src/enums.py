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
    # Долгое ожидание без ответа провайдера: авто-перепроверка прекращена,
    # повторная проверка — только вручную (admin recheck).
    WAIT = "wait"


TopupStatus = PayStatus


class PayDirective:
    """Директива запуска callback-скрипта платежа."""

    WEBHOOK = "webhook"  # входящий вебхук провайдера — доверяем ответу
    RECHECK = "recheck"  # инициировано нами — скрипт перепроверяет апстрим


class ServiceAction:
    """Действия жизненного цикла выданной услуги (передаются в lua-шаблон)."""

    CREATE = "create"
    RENEW = "renew"
    STOP = "stop"
    DELETE = "delete"
    FREEZE = "freeze"


class UsvcState:
    """Состояние выданной услуги (независимо от статуса доставки)."""

    ACTIVE = "active"
    FROZEN = "frozen"
    STOPPED = "stopped"
    EXPIRED = "expired"


class TaskKind:
    """Вид задачи в очереди billing-loop."""

    SVC_ACTION = "svc_action"  # действие над услугой (напр. истечение)
    PAY_RECHECK = "pay_recheck"  # перепроверка статуса платежа


class TaskStatus:
    """Статус задачи в очереди billing_tasks."""

    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    WAIT = "wait"  # отложена без авто-повтора (ждёт ручного триггера)


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
    "PayDirective",
    "PayTarget",
    "ServiceAction",
    "UsvcState",
    "TaskKind",
    "TaskStatus",
    "PromoKind",
    "DiscountType",
    "ScriptKind",
]
