"""Реестр настроек, хранимых в таблице ``settings`` (key-value в БД)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


# Кастеры строкового значения настройки к нужному типу.
def _to_bool(raw: str) -> bool:
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _to_int(raw: str) -> int:
    return int(raw)


_CASTERS: dict[str, Callable[[str], Any]] = {
    "str": str,
    "int": _to_int,
    "bool": _to_bool,
}


@dataclass(frozen=True)
class SettingDef:
    """Описание одной настройки в БД.

    :arg key:    ключ настройки (``smtp.host``, ``role.owner`` …).
    :arg source: имя атрибута ``AppConfig`` — источник для первичного сидинга.
    :arg type:   тип значения (``str|int|bool``).
    :arg secret: шифровать ли значение в БД (через SecBox).
    :arg group:  логическая группа (для админки и ``get_group``).
    :arg desc:   человекочитаемое описание.
    """

    key: str
    source: str | None
    type: str = "str"
    secret: bool = False
    group: str = "general"
    desc: str = ""

    def cast(self, raw: str) -> Any:
        """Привести строковое значение из БД к типу настройки."""
        return _CASTERS[self.type](raw)


# --- Каталог настроек --------------------------------------------------------
SETTINGS: tuple[SettingDef, ...] = (
    # SMTP
    SettingDef("smtp.host", "SMTP_HOST", group="smtp", desc="SMTP сервер"),
    SettingDef("smtp.port", "SMTP_PORT", type="int", group="smtp", desc="SMTP порт"),
    SettingDef("smtp.user", "SMTP_USER", group="smtp", desc="SMTP логин"),
    SettingDef("smtp.pass", "SMTP_PASS", secret=True, group="smtp", desc="SMTP пароль"),
    SettingDef("smtp.from", "SMTP_FROM", group="smtp", desc="Адрес отправителя"),
    SettingDef(
        "smtp.tls", "SMTP_TLS", type="bool", group="smtp", desc="Использовать TLS"
    ),
    # Почтовые коды (подтверждение email / сброс пароля)
    SettingDef(
        "mail.code_ttl",
        "VERIFY_TOKEN_TTL",
        type="int",
        group="mail",
        desc="TTL кода подтверждения email и сброса пароля, секунды",
    ),
    SettingDef(
        "mail.code_digits",
        None,
        type="int",
        group="mail",
        desc="Длина числового кода подтверждения email, цифр",
    ),
    SettingDef(
        "password.reset.method",
        None,
        group="mail",
        desc="Способ сброса пароля: 'code' (числовой код по email), "
        "'token' (ссылка с временным токеном по email), 'authenticated' "
        "(email-сброс выключен, только смена пароля в профиле по старому "
        "паролю) или 'disabled' (сброс пароля недоступен вообще)",
    ),
    # Имена базовых ролей
    SettingDef("role.owner", "ROLE_OWNER", group="role", desc="Имя роли владельца"),
    SettingDef(
        "role.admin", "ROLE_ADMIN", group="role", desc="Имя роли администратора"
    ),
    SettingDef("role.manager", "ROLE_MANAGER", group="role", desc="Имя роли менеджера"),
    SettingDef("role.support", "ROLE_SUPPORT", group="role", desc="Имя роли поддержки"),
    SettingDef("role.media", "ROLE_MEDIA", group="role", desc="Имя роли медиа-модерации (резерв)"),
    SettingDef("role.user", "ROLE_USER", group="role", desc="Имя роли пользователя"),
    SettingDef("role.guest", "ROLE_GUEST", group="role", desc="Имя роли гостя"),
    SettingDef("role.banned", "ROLE_BANNED", group="role", desc="Имя роли блокировки"),
    # Реферальная программа
    SettingDef(
        "referral.percent",
        "REFERRAL_PERCENT",
        type="int",
        group="referral",
        desc="Глобальный процент отчислений рефереру (бонусный баланс), %",
    ),
    # Флаги состояния системы (выставляются bootstrap-проверками, без сидинга)
    SettingDef(
        "system.fs_insecure",
        None,
        type="bool",
        group="system",
        desc="Небезопасные права на файлы data/* (выставляется access-проверкой)",
    ),
    # Триггеры: анти-петля и повторные попытки
    SettingDef(
        "triggers.max_retries",
        None,
        type="int",
        group="triggers",
        desc="Максимум попыток выполнения одного действия триггера",
    ),
    SettingDef(
        "triggers.max_fires_per_event_per_minute",
        None,
        type="int",
        group="triggers",
        desc="Анти-петля: лимит срабатываний одного события в минуту",
    ),
    # Анти-брутфорс логина (доп. блокировка поверх общего rate_limit)
    SettingDef(
        "auth.lockout.max_attempts",
        None,
        type="int",
        group="auth",
        desc="Порог неудачных попыток входа (по логину/IP) до временной блокировки",
    ),
    SettingDef(
        "auth.lockout.window_sec",
        None,
        type="int",
        group="auth",
        desc="Длительность блокировки/окна счётчика неудачных попыток входа, секунды",
    ),
    # Lua: таймаут вызова и ретраи (мягкая, настраиваемая изоляция вызовов воркера)
    SettingDef(
        "lua.call_timeout_sec",
        "LUA_CALL_TIMEOUT",
        type="int",
        group="lua",
        desc="Таймаут одного вызова к LuaWorker, секунды",
    ),
    SettingDef(
        "lua.max_retries",
        None,
        type="int",
        group="lua",
        desc="Сколько раз повторить вызов LuaWorker при таймауте, прежде чем "
        "вернуть ошибку",
    ),
    SettingDef(
        "lua.retry_backoff_sec",
        None,
        type="int",
        group="lua",
        desc="Пауза перед повтором вызова LuaWorker, секунды",
    ),
    # Медиа: грейс-период очистки "осиротевших" записей (анти-TOCTOU)
    SettingDef(
        "media.cleanup_grace_sec",
        None,
        type="int",
        group="media",
        desc="Не удалять при очистке медиа-записи младше этого возраста, секунды "
        "(защита от удаления только что загруженного, ещё не привязанного файла)",
    ),
    # Аналитика: продвинутый уровень (Polars) — кэш и параметры расчётов
    SettingDef(
        "analytics.advanced.cache_ttl_sec",
        None,
        type="int",
        group="analytics",
        desc="TTL кэша сводки продвинутой аналитики в Valkey, секунды",
    ),
    SettingDef(
        "analytics.churn.inactive_days",
        None,
        type="int",
        group="analytics",
        desc="Порог неактивности (дней без paid-платежа) для расчёта churn-rate",
    ),
)

_BY_KEY: dict[str, SettingDef] = {d.key: d for d in SETTINGS}


def by_key(key: str) -> SettingDef | None:
    """Найти описание настройки по ключу (или ``None``, если не зарегистрирована)."""
    return _BY_KEY.get(key)


def seed_defs() -> tuple[SettingDef, ...]:
    """Настройки, подлежащие сидингу из окружения (у которых задан ``source``)."""
    return tuple(d for d in SETTINGS if d.source is not None)


def group_keys(group: str) -> tuple[str, ...]:
    """Ключи настроек заданной группы."""
    return tuple(d.key for d in SETTINGS if d.group == group)


__all__ = ["SettingDef", "SETTINGS", "by_key", "seed_defs", "group_keys"]
