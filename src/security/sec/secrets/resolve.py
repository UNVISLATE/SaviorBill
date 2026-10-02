"""Разрешение секретов приложения через выбранное хранилище.

Заполняет в конфигурации значения секретов: генерируемые (ключ шифрования,
JWT-ключевая пара, сервисный токен Lua) создаются при отсутствии, предоставляемые
(пароль БД/SMTP, ключ S3) читаются из хранилища с откатом на прямое значение ENV.
"""

from __future__ import annotations

import logging
import secrets as _secrets

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from core.config import AppConfig
from security.sec.box import SecBox

from .base import SecretName, SecretResolver
from . import build_secret_store

log = logging.getLogger("saviorbill.secrets")


def _generate_jwt_keypair() -> tuple[str, str]:
    """Сгенерировать пару RSA-2048 ключей для подписи JWT (RS256).

    :return: ``(private_pem, public_pem)`` — PKCS8-приватный и SPKI-публичный,
        без пароля (приватный ключ и так лежит только в защищённом хранилище).
    """
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    return private_pem, public_pem


def _new_kid() -> str:
    """Короткий уникальный идентификатор ключа для заголовка JWT ``kid``."""
    return _secrets.token_hex(8)


def _ensure_jwt_keypair(
    res: SecretResolver, cfg: AppConfig, *, allow_env_fallback: bool
) -> tuple[str, str, str]:
    """Прочитать существующую RS256-пару+kid или сгенерировать новую (атомарно вместе).

    В отличие от прочих генерируемых секретов, приватный ключ, публичный ключ
    и ``kid`` должны создаваться и сохраняться вместе за один проход — иначе
    можно получить несовпадающую тройку при частичном сбое между ``ensure()``.
    """
    private_pem = res.store.get(SecretName.JWT_PRIVATE) or (
        cfg.JWT_PRIVATE_KEY if allow_env_fallback else None
    )
    public_pem = res.store.get(SecretName.JWT_PUBLIC) or (
        cfg.JWT_PUBLIC_KEY if allow_env_fallback else None
    )
    kid = res.store.get(SecretName.JWT_KID) or (
        cfg.JWT_KID if allow_env_fallback else None
    )
    if private_pem and public_pem and kid:
        return private_pem, public_pem, kid
    if private_pem or public_pem or kid:
        raise RuntimeError(
            "incomplete JWT keypair in storage: private/public/kid must all be "
            "present or all absent — remove the remaining parts to regenerate"
        )
    private_pem, public_pem = _generate_jwt_keypair()
    kid = _new_kid()
    res.store.put(SecretName.JWT_PRIVATE, private_pem)
    res.store.put(SecretName.JWT_PUBLIC, public_pem)
    res.store.put(SecretName.JWT_KID, kid)
    log.info("generated a new RS256 JWT keypair (kid=%s)", kid)
    return private_pem, public_pem, kid


def rotate_jwt_keypair(cfg: AppConfig) -> str:
    """Сгенерировать новый ключ подписи JWT, сохранив текущий как «предыдущий».

    Старый ключ остаётся доступным только для верификации (``jwt_public_keys()``)
    на время grace-периода — уже выданные access/refresh-токены с его ``kid``
    не станут невалидными мгновенно, в отличие от полной смены ключа целиком
    (см. AUDIT.md §1.5). Вызывается вручную оператором (см. ``src/jwtctl.py``),
    не автоматически при каждом запуске.

    :return: новый ``kid``.
    """
    store = build_secret_store(cfg)
    if not (cfg.JWT_PRIVATE_KEY and cfg.JWT_PUBLIC_KEY and cfg.JWT_KID):
        raise RuntimeError("no current JWT keypair to rotate — resolve_secrets() first")

    new_private, new_public = _generate_jwt_keypair()
    new_kid = _new_kid()

    # Текущий ключ становится предыдущим (заменяя более старый previous, если был).
    store.put(SecretName.JWT_PUBLIC_PREV, cfg.JWT_PUBLIC_KEY)
    store.put(SecretName.JWT_KID_PREV, cfg.JWT_KID)
    store.put(SecretName.JWT_PRIVATE, new_private)
    store.put(SecretName.JWT_PUBLIC, new_public)
    store.put(SecretName.JWT_KID, new_kid)

    cfg.JWT_PUBLIC_KEY_PREV = cfg.JWT_PUBLIC_KEY
    cfg.JWT_KID_PREV = cfg.JWT_KID
    cfg.JWT_PRIVATE_KEY = new_private
    cfg.JWT_PUBLIC_KEY = new_public
    cfg.JWT_KID = new_kid
    log.warning("rotated the JWT keypair (new kid=%s, previous kid preserved for grace period)", new_kid)
    return new_kid


def resolve_secrets(cfg: AppConfig) -> str:
    """Разрешить все секреты приложения и записать их в ``cfg``.

    :arg cfg: конфигурация приложения (мутируется).
    :return: имя использованного бэкенда секретов.
    """
    store = build_secret_store(cfg)
    res = SecretResolver(store)
    allow_env_fallback = cfg.DEBUG or cfg.SECRETS_ALLOW_ENV_FALLBACK
    if allow_env_fallback and not cfg.DEBUG:
        log.warning(
            "secret ENV fallback is explicitly enabled; use only during bootstrap"
        )

    def env_fallback(value: str | None) -> str | None:
        if value and allow_env_fallback:
            log.warning("using an ENV fallback for a missing secret")
            return value
        return None

    # Генерируемые секреты: создаются один раз, затем переиспользуются.
    # SECRETS_KEY сразу в версионированном формате (см. SecBox.new_versioned_key) —
    # будущая ротация не потребует миграции формата.
    cfg.SECRETS_KEY = res.ensure(
        SecretName.SECRETS_KEY,
        SecBox.new_versioned_key,
        fallback=env_fallback(cfg.SECRETS_KEY),
    )
    cfg.AUTH_SESSION_HASH_KEY = res.ensure(
        SecretName.AUTH_SESSION_HASH_KEY,
        lambda: _secrets.token_urlsafe(32),
        fallback=env_fallback(cfg.AUTH_SESSION_HASH_KEY),
    )
    cfg.JWT_PRIVATE_KEY, cfg.JWT_PUBLIC_KEY, cfg.JWT_KID = _ensure_jwt_keypair(
        res, cfg, allow_env_fallback=allow_env_fallback
    )
    # Предыдущий ключ (после ротации) — необязателен, только на чтение.
    cfg.JWT_PUBLIC_KEY_PREV = res.store.get(SecretName.JWT_PUBLIC_PREV) or (
        cfg.JWT_PUBLIC_KEY_PREV if allow_env_fallback else None
    )
    cfg.JWT_KID_PREV = res.store.get(SecretName.JWT_KID_PREV) or (
        cfg.JWT_KID_PREV if allow_env_fallback else None
    )
    cfg.LUA_SERVICE_TOKEN = res.ensure(
        SecretName.LUA_TOKEN,
        lambda: _secrets.token_urlsafe(32),
        fallback=env_fallback(cfg.LUA_SERVICE_TOKEN),
    )

    # Предоставляемые секреты: только чтение; ENV fallback — только в
    # development/bootstrap режиме, не как production policy.
    cfg.DB_PASS = res.ensure(SecretName.DB_PASS, fallback=env_fallback(cfg.DB_PASS))
    cfg.SMTP_PASS = res.ensure(
        SecretName.SMTP_PASS, fallback=env_fallback(cfg.SMTP_PASS)
    )
    cfg.S3_SECRET = res.ensure(
        SecretName.S3_SECRET, fallback=env_fallback(cfg.S3_SECRET)
    )

    if not cfg.JWT_PRIVATE_KEY or not cfg.JWT_PUBLIC_KEY or not cfg.JWT_KID:
        raise RuntimeError("JWT keypair is not resolved from either storage or ENV")
    if not cfg.DB_PASS:
        raise RuntimeError("DB_PASS is not allowed from either storage or ENV")

    log.info("secrets are allowed through the backend %r", store.name)
    return store.name


__all__ = ["resolve_secrets", "rotate_jwt_keypair"]
