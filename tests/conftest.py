"""Общие фикстуры и настройка окружения для тестов.

Здесь выставляем безопасные значения переменных окружения ДО импорта
приложения (``app.py`` создаёт ``AppConfig()`` на уровне модуля, а у конфига
есть обязательные поля ``DB_PASS`` и ``JWT_PRIVATE_KEY``/``JWT_PUBLIC_KEY``).
"""

from __future__ import annotations

import os
from functools import lru_cache

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


@lru_cache(maxsize=1)
def _rsa_keypair() -> tuple[str, str]:
    """:return: ``(private_pem, public_pem)`` — тестовая RS256-пара (2048 бит).

    Генерация RSA не бесплатна — кешируем на уровне процесса вместо
    перегенерации в каждом тесте/файле.
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


@pytest.fixture(scope="session")
def rsa_keypair() -> tuple[str, str]:
    """Тестовая RS256-пара для тестов, которым нужны реальные PEM-ключи."""
    return _rsa_keypair()


# Значения по умолчанию для конфига. Интеграционные тесты переопределяют
# DB_HOST/VALKEY_HOST через окружение deploy/test/docker-compose.yml.
os.environ.setdefault("DB_PASS", "test")
_priv, _pub = _rsa_keypair()
os.environ.setdefault("JWT_PRIVATE_KEY", _priv)
os.environ.setdefault("JWT_PUBLIC_KEY", _pub)
os.environ.setdefault("JWT_KID", "test-kid")
os.environ.setdefault("PAY_CALLBACK_SECRET", "test-callback-secret")
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("VALKEY_HOST", "localhost")


