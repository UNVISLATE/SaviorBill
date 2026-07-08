"""Разрешение секретов приложения через выбранное хранилище.

Заполняет в конфигурации значения секретов: генерируемые (ключ шифрования,
JWT-ключ, сервисный токен Lua) создаются при отсутствии, предоставляемые
(пароль БД/SMTP, ключ S3) читаются из хранилища с откатом на прямое значение ENV.
"""

from __future__ import annotations

import logging
import secrets as _secrets

from utils.config import AppConfig
from utils.sec.box import SecBox

from .base import SecretName, SecretResolver
from . import build_secret_store

log = logging.getLogger("saviorbill.secrets")


def resolve_secrets(cfg: AppConfig) -> str:
    """Разрешить все секреты приложения и записать их в ``cfg``.

    :arg cfg: конфигурация приложения (мутируется).
    :return: имя использованного бэкенда секретов.
    """
    store = build_secret_store(cfg)
    res = SecretResolver(store)

    # Генерируемые секреты: создаются один раз, затем переиспользуются.
    # SECRETS_KEY сразу в версионированном формате (см. SecBox.new_versioned_key) —
    # будущая ротация не потребует миграции формата.
    cfg.SECRETS_KEY = res.ensure(
        SecretName.SECRETS_KEY, SecBox.new_versioned_key, fallback=cfg.SECRETS_KEY
    )
    cfg.JWT_SECRET = res.ensure(
        SecretName.JWT, lambda: _secrets.token_urlsafe(48), fallback=cfg.JWT_SECRET
    )
    cfg.LUA_SERVICE_TOKEN = res.ensure(
        SecretName.LUA_TOKEN,
        lambda: _secrets.token_urlsafe(32),
        fallback=cfg.LUA_SERVICE_TOKEN,
    )

    # Предоставляемые секреты: только чтение, откат на прямое значение ENV.
    cfg.DB_PASS = res.ensure(SecretName.DB_PASS, fallback=cfg.DB_PASS)
    cfg.SMTP_PASS = res.ensure(SecretName.SMTP_PASS, fallback=cfg.SMTP_PASS)
    cfg.S3_SECRET = res.ensure(SecretName.S3_SECRET, fallback=cfg.S3_SECRET)

    if not cfg.JWT_SECRET:
        raise RuntimeError("JWT_SECRET is not resolved from either storage or ENV")
    if not cfg.DB_PASS:
        raise RuntimeError("DB_PASS is not allowed from either storage or ENV")

    log.info("secrets are allowed through the backend %r", store.name)
    return store.name


__all__ = ["resolve_secrets"]
