"""Fail-fast проверка опасных дефолтов из ``deploy/.env.example``.

Вызывается первым в ``lifespan``, до подключения к БД/Valkey — если в
проде (``DEBUG=false``) остались значения-плейсхолдеры из примера
(``DB_PASS=change-me``, ``OWNER_LOGIN=owner``/``OWNER_PASS=owner``,
``TRUSTED_PROXIES=*``) или не задан ``BUS_SIGNING_KEY``, приложение не
должно тихо стартовать с ними: либо забытый
плейсхолдер держит дверь открытой (any-IP доверенный прокси = спуфинг
X-Forwarded-For), либо это ровно тот пароль/логин, который есть в
публичном примере в репозитории, либо шина задач/результатов вообще не
защищена от подделки сообщений.
"""

from __future__ import annotations

from core.config import AppConfig

_DANGEROUS_DB_PASS = {"change-me", "changeme", "password", ""}
_DANGEROUS_OWNER_CREDS = {"owner", "admin", "password", "changeme"}


class InsecureDefaultsError(RuntimeError):
    """В проде (``DEBUG=false``) обнаружен небезопасный дефолт из примера."""


def check_dangerous_defaults(cfg: AppConfig) -> None:
    """Бросить :class:`InsecureDefaultsError`, если найден опасный дефолт.

    В режиме разработки (``DEBUG=true``) проверка не выполняется — там
    известные тестовые креды — осознанное удобство, а не риск.
    """
    if cfg.DEBUG:
        return

    problems: list[str] = []

    if "*" in cfg.trusted_proxies_list:
        problems.append(
            "TRUSTED_PROXIES=* доверяет X-Forwarded-For от любого клиента "
            "(spoofing IP) — укажите точный список IP/подсетей reverse-proxy"
        )

    db_pass = (cfg.DB_PASS or "").strip().lower()
    if db_pass in _DANGEROUS_DB_PASS:
        problems.append(
            "DB_PASS не задан или равен плейсхолдеру из .env.example "
            "— задайте случайный пароль базы данных"
        )

    owner_login = (cfg.OWNER_LOGIN or "").strip().lower()
    owner_pass = (cfg.OWNER_PASS or "").strip().lower()
    if owner_login in _DANGEROUS_OWNER_CREDS and owner_pass in _DANGEROUS_OWNER_CREDS:
        problems.append(
            "OWNER_LOGIN/OWNER_PASS равны публично известным значениям из "
            ".env.example — задайте собственные учётные данные владельца"
        )

    if not (cfg.BUS_SIGNING_KEY or "").strip():
        problems.append(
            "BUS_SIGNING_KEY не задан — без него lua:tasks/lua:results/"
            "media:tasks/media:results не подписываются, и любой процесс с "
            "доступом к Valkey может подделать задачу или результат воркера; "
            "сгенерируйте общий секрет для billing/luaworker/mediaworker"
        )

    if problems:
        raise InsecureDefaultsError(
            "отказ старта: обнаружены небезопасные значения ENV (DEBUG=false). "
            + "; ".join(problems)
        )


__all__ = ["check_dangerous_defaults", "InsecureDefaultsError"]
