"""Реестр настроек, хранимых в таблице ``settings`` (key-value в БД)."""

from __future__ import annotations

import json
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
    "json": json.loads,
}


@dataclass(frozen=True)
class SettingDef:
    """Описание одной настройки в БД.

    :arg key:      ключ настройки (``smtp.host``, ``ui.admin.name`` …).
    :arg source:   имя атрибута ``AppConfig`` — источник для первичного сидинга.
    :arg type:     тип значения (``str|int|bool``).
    :arg secret:   шифровать ли значение в БД (через SecBox).
    :arg system:   внутренний служебный флаг платформы.
    :arg protected: значение можно редактировать через админку, но НЕЛЬЗЯ удалить.
    :arg group:    логическая группа (для админки и ``get_group``).
    :arg desc:     человекочитаемое описание.
    """

    key: str
    source: str | None
    type: str = "str"
    secret: bool = False
    system: bool = False
    protected: bool = False
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
    # Имена базовых ролей больше НЕ хранятся здесь: Role.name уже пишется в
    # БД при первом запуске (см. utils/init/role.py), а settings-копия имени
    # никогда не перечитывается после инициализации — она была мёртвым
    # "украшением" в admin Raw Settings (выглядит редактируемым, но правка
    # ни на что не влияет). Имя роли теперь читается только из ENV в момент
    # инициализации (см. utils/init/__init__.py::_role_names) и нигде не
    # дублируется в settings.
    # Реферальная программа
    SettingDef(
        "referral.percent",
        "REFERRAL_PERCENT",
        type="int",
        group="referral",
        desc="Глобальный процент отчислений рефереру (бонусный баланс), %",
    ),
    # Флаги состояния системы (выставляются bootstrap-проверками/инициализацией,
    # не подлежат ручной правке или удалению через admin settings API — см.
    # SettingDef.system).
    SettingDef(
        "system.initialized",
        None,
        type="bool",
        group="system",
        system=True,
        desc="Первичная инициализация уже выполнена (единый флаг; выставляется "
        "utils/init один раз и больше не должен трогаться вручную)",
    ),
    SettingDef(
        "system.fs_insecure",
        None,
        type="bool",
        group="system",
        system=True,
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
    # Медиа: лимиты загрузки — редактируются из админки без передеплоя
    # mediaworker (он читает те же ключи из settings/Valkey-кэша, см.
    # mediaworker/src/utils/settings.py).
    SettingDef(
        "media.small_max_bytes",
        "MEDIA_SMALL_MAX_BYTES",
        type="int",
        group="media",
        desc="Лимит байт для аккаунтов без media.uploadlarge",
    ),
    SettingDef(
        "media.max_bytes",
        "MEDIA_MAX_BYTES",
        type="int",
        group="media",
        desc="Лимит байт для аккаунтов с media.uploadlarge",
    ),
    SettingDef(
        "media.uploads_per_hour",
        "MEDIA_UPLOADS_PER_HOUR",
        type="int",
        group="media",
        desc="Загрузок в час для аккаунтов без media.uploadlarge "
        "(у media.uploadlarge часовой лимит не применяется)",
    ),
    SettingDef(
        "user.media.limit",
        "USER_MEDIA_LIMIT",
        type="int",
        group="media",
        desc="Максимум медиа-файлов на аккаунт (без media.uploadlarge/"
        "admin.media.upload — у них лимит не применяется)",
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
    # UI/брендинг: admin-панель и клиентское приложение.
    # ``name`` — единственная настройка, которая гарантированно сидится при
    # первом запуске (см. utils/init/settings.py) — public-роут
    # api/v1/branding.py читает её как есть, не изобретая дефолт "на лету".
    # ``protected`` — можно менять, но нельзя удалить: без неё branding
    # эндпоинт остался бы без названия (в таблице кроме name ничего гарантированно
    # нет — logo/favicon/theme опциональны и заполняются вручную из админки).
    SettingDef(
        "ui.admin.name",
        "UI_ADMIN_NAME",
        group="ui",
        protected=True,
        desc="Название в шапке/тайтле admin UI",
    ),
    SettingDef("ui.admin.logo", None, group="ui", desc="Токен медиа логотипа admin UI"),
    SettingDef(
        "ui.admin.favicon", None, group="ui", desc="Токен медиа favicon admin UI"
    ),
    SettingDef(
        "ui.admin.theme",
        None,
        type="json",
        group="ui",
        desc="Произвольная JSON-тема admin UI",
    ),
    SettingDef(
        "ui.client.name",
        "UI_CLIENT_NAME",
        group="ui",
        protected=True,
        desc="Название клиентского приложения",
    ),
    SettingDef("ui.client.logo", None, group="ui", desc="Токен медиа логотипа клиента"),
    SettingDef(
        "ui.client.favicon", None, group="ui", desc="Токен медиа favicon клиента"
    ),
    SettingDef(
        "ui.client.theme",
        None,
        type="json",
        group="ui",
        desc="Произвольная JSON-тема клиента",
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
