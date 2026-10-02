"""Базовые контракты хранилищ секретов.

Политика: file backend использует файлы и ENV как локальные источники
секретов; внешние менеджеры секретов являются отдельным явным источником.
Генерируемые секреты создаются один раз (если их ещё нет) и переиспользуются.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable


class SecretName:
    """Логические имена управляемых секретов."""

    SECRETS_KEY = "secrets_key"  # ключ Fernet для шифрования секретов в БД
    AUTH_SESSION_HASH_KEY = "auth_session_hash_key"
    JWT_PRIVATE = "jwt_private_key"  # приватный ключ подписи JWT (RS256, billing-only)
    JWT_PUBLIC = "jwt_public_key"  # публичный ключ проверки JWT (billing + mediaworker)
    JWT_KID = "jwt_kid"  # идентификатор текущего ключа (заголовок JWT ``kid``)
    JWT_PUBLIC_PREV = "jwt_public_key_prev"  # предыдущий ключ (grace-период после ротации)
    JWT_KID_PREV = "jwt_kid_prev"
    LUA_TOKEN = "lua_service_token"  # сервисный токен LuaWorker
    DB_PASS = "db_pass"  # пароль БД (только чтение)
    SMTP_PASS = "smtp_pass"  # пароль SMTP (только чтение)
    S3_SECRET = "s3_secret"  # секретный ключ S3 (только чтение)


class SecretStore(ABC):
    """Источник секретов (файлы или облачный менеджер)."""

    #: человекочитаемое имя бэкенда (для логов).
    name: str = "base"

    @abstractmethod
    def get(self, key: str) -> str | None:
        """Прочитать значение секрета.

        :arg key: логическое имя секрета.
        :return: значение или ``None`` если секрета нет.
        """

    @abstractmethod
    def put(self, key: str, value: str) -> None:
        """Создать/записать значение секрета.

        :arg key: логическое имя секрета.
        :arg value: значение для сохранения.
        """

    def exists(self, key: str) -> bool:
        """Есть ли секрет в хранилище.

        :arg key: логическое имя секрета.
        :return: ``True`` если значение присутствует.
        """
        return self.get(key) is not None


class SecretResolver:
    """Разрешение секретов по политике «создать-если-нет, затем читать»."""

    def __init__(self, store: SecretStore) -> None:
        self.store = store

    def ensure(
        self,
        key: str,
        generator: Callable[[], str] | None = None,
        fallback: str | None = None,
    ) -> str | None:
        """Вернуть секрет, при необходимости сгенерировав и сохранив его.

        Приоритет: значение из хранилища → прямое значение из ENV (``fallback``)
        → генерация (с записью в хранилище). Так оператор может переопределить
        секрет через ENV, не ломая «создать-если-нет» для пустого хранилища.

        :arg key: логическое имя секрета.
        :arg generator: функция генерации (для создаваемых секретов).
        :arg fallback: прямое значение из ENV (override для dev/legacy).
        :return: значение секрета или ``None``.
        """
        existing = self.store.get(key)
        if existing:
            return existing
        if fallback:
            return fallback
        if generator is not None:
            value = generator()
            self.store.put(key, value)
            return value
        return None


__all__ = ["SecretName", "SecretStore", "SecretResolver"]
