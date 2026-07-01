from __future__ import annotations


class Delivery:
    """Способ доставки услуги."""

    KEY = "key"  # выдача готовым цифровым ключом из пула
    LUA = "lua"  # выдача через исполнение Lua-скрипта


class UsvcStatus:
    """Единый статус выданной услуги (объединяет доставку и состояние ЖЦ).

    Заменяет прежнюю пару ``OrderStatus`` (доставка) + ``UsvcState`` (состояние),
    которые дублировали друг друга.
    """

    PENDING = "pending"  # создана, ждёт оплаты/доставки
    ACTIVE = "active"  # доставлена и действует
    FROZEN = "frozen"  # временно заморожена
    STOPPED = "stopped"  # остановлена (вручную/по действию)
    EXPIRED = "expired"  # истёк срок действия
    FAILED = "failed"  # доставка не удалась
    CANCELLED = "cancelled"  # отменена


class PayStatus:
    """Статус платежа (денежной транзакции через провайдера)."""

    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    REFUNDED = "refunded"  # средства возвращены плательщику
    # Долгое ожидание без ответа провайдера: авто-перепроверка прекращена,
    # повторная проверка — только вручную (admin recheck).
    WAIT = "wait"


TopupStatus = PayStatus


class PayAction:
    """Действие платёжного скрипта (единый скрипт провайдера, action-driven).

    ``create``/``callback`` — обязательны для любого платёжного скрипта;
    ``check``/``refund`` — опциональны (заявляются в поддерживаемых действиях).
    """

    CREATE = "create"  # инициализация платежа (вернуть ссылку оплаты)
    CALLBACK = "callback"  # входящий вебхук — доверяем подписи скрипта
    CHECK = "check"  # перепроверка статуса у API провайдера (инициируем сами)
    REFUND = "refund"  # возврат средств

    MANDATORY = (CREATE, CALLBACK)
    ALL = (CREATE, CALLBACK, CHECK, REFUND)


class ServiceAction:
    """Действия жизненного цикла выданной услуги (передаются в lua-шаблон)."""

    CREATE = "create"
    RENEW = "renew"
    STOP = "stop"
    DELETE = "delete"
    FREEZE = "freeze"


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
    TRIGGER = "trigger"  # действие триггера


class BaseRole:
    """Стабильные ключи базовых ролей (не зависят от переименования в БД).

    ``Role.key`` хранит один из этих ключей для системных ролей и служит основой
    производных флагов пользователя (активен/верифицирован).
    """

    OWNER = "owner"
    ADMIN = "admin"
    MANAGER = "manager"
    SUPPORT = "support"
    USER = "user"  # верифицированный пользователь
    GUEST = "guest"  # только что зарегистрирован (== is_verified false)
    BANNED = "banned"  # заблокирован (== is_active false)


__all__ = [
    "Delivery",
    "UsvcStatus",
    "PayStatus",
    "TopupStatus",
    "PayAction",
    "PayTarget",
    "ServiceAction",
    "PromoKind",
    "DiscountType",
    "ScriptKind",
    "BaseRole",
]
