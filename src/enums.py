from __future__ import annotations


class Delivery:
    """Способ доставки услуги."""

    KEY = "key"  # выдача готовым цифровым ключом из пула
    LUA = "lua"  # выдача через исполнение Lua-скрипта


class UsvcStatus:
    """Статусы выданных услуг (объединяет доставку и состояние).
    """

    PENDING = "pending"  # создана, ждёт оплаты/доставки
    PROVISIONING = "provisioning"  # асинхронное создание на внешней панели
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
    REFUNDING = "refunding"
    REVIEW = "review"
    FAILED = "failed"
    REFUNDED = "refunded"
    WAIT = "wait"
    CANCELLED = "cancelled"


TopupStatus = PayStatus


class PayAction:
    """Действие платёжного скрипта (единый скрипт провайдера, action-driven)."""

    CREATE = "create"  # инициализация платежа (вернуть ссылку оплаты)
    CALLBACK = "callback"  # входящий вебхук — доверяем подписи скрипта
    CHECK = "check"  # перепроверка статуса у API провайдера (инициируем сами)
    REFUND = "refund"  # возврат средств

    MANDATORY = (CREATE, CALLBACK)
    ALL = (CREATE, CALLBACK, CHECK, REFUND)


class ServiceAction:
    """Действия жизненного цикла выданной услуги (передаются в lua-шаблон)."""

    CREATE = "create"
    POLL = "poll"
    RENEW = "renew"
    STOP = "stop"
    START = "start"
    DELETE = "delete"
    FREEZE = "freeze"
    UNFREEZE = "unfreeze"
    RECONFIGURE = "reconfigure"
    UPGRADE = "upgrade"


class PayTarget:
    """Назначение платежа: пополнить баланс или оплатить/продлить/апгрейдить услугу."""

    BALANCE = "balance"
    SERVICE = "service"
    RENEW = "renew"
    UPGRADE = "upgrade"


class PromoKind:
    """Тип промокода."""

    BONUS = "bonus"  # пополнение бонусного баланса
    DISCOUNT = "discount"  # скидка на товар (применяется при заказе)
    SERVICE = "service"  # выдача услуги по промокоду


class DiscountType:
    """Как трактовать значение скидочного промокода."""

    PERCENT = "percent"
    FIXED = "fixed"


class PriceType:
    """Тип ценообразования услуги."""

    FIXED = "fixed"  # фиксированная цена (по умолчанию)
    CUSTOM = "custom"  # произвольная сумма (Steam/пополнения)
    TIERED = "tiered"  # тарифная сетка (периоды/тарифы)
    CONFIGURABLE = "configurable"  # конфигуратор ресурсов (VDS/хостинг)

    ALL = (FIXED, CUSTOM, TIERED, CONFIGURABLE)


class AuthAction:
    """Действие OAuth-скрипта (единый скрипт провайдера, action-driven)."""

    START = "start"  # подготовка authorize_url для редиректа
    CALLBACK = "callback"  # обмен кода на профиль (sub/email/…)

    MANDATORY = (START, CALLBACK)
    ALL = (START, CALLBACK)


class ScriptKind:
    """Назначение Lua-скрипта."""

    SERVICE = "service"  # доставка услуги
    PAYMENT = "payment"  # платёжная интеграция
    AUTH = "auth"  # OAuth-интеграция (вход через провайдера)
    GENERIC = "generic"  # прочее
    TRIGGER = "trigger"  # действие триггера
    EMAIL = "email"  # почтовый транспорт (отправка писем через API провайдера)


class BaseRole:
    """Стабильные ключи базовых ролей (не зависят от переименования в БД)."""

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
    "AuthAction",
    "PayTarget",
    "ServiceAction",
    "PromoKind",
    "DiscountType",
    "PriceType",
    "ScriptKind",
    "BaseRole",
]
