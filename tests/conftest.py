"""Общие фикстуры и настройка окружения для тестов.

Здесь выставляем безопасные значения переменных окружения ДО импорта
приложения (``app.py`` создаёт ``AppConfig()`` на уровне модуля, а у конфига
есть обязательные поля ``DB_PASS`` и ``JWT_SECRET``).
"""

from __future__ import annotations

import os

# Значения по умолчанию для конфига. Интеграционные тесты переопределяют
# DB_HOST/VALKEY_HOST через окружение deploy/test/docker-compose.yml.
os.environ.setdefault("DB_PASS", "test")
os.environ.setdefault("JWT_SECRET", "test-secret-please-change")
os.environ.setdefault("PAY_CALLBACK_SECRET", "test-callback-secret")
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("VALKEY_HOST", "localhost")
