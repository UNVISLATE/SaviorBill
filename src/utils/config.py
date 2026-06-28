from __future__ import annotations

from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from sqlalchemy.engine.url import URL


class AppConfig(BaseSettings):
    """Конфигурация приложения"""

    APP_NAME: str = Field(default="SaviorBill")
    APP_VERSION: str = Field(default="0.0.1dev")

    HOST: str = Field(default="0.0.0.0")
    PORT: int = Field(default=8000)
    DEBUG: bool = Field(default=False)

    # DB
    DB_DRIVER: str = Field(default="postgresql+asyncpg")
    DB_USER: str = Field(default="aiosupport")
    DB_PASS: str
    DB_HOST: str = Field(default="localhost")
    DB_PORT: int = Field(default=5432)
    DB_NAME: str = Field(default="aiosupport")

    # Valkey / Redis
    VALKEY_HOST: str = Field(default="localhost")
    VALKEY_PORT: int = Field(default=6379)
    VALKEY_DB: int = Field(default=0)

    # --- Auth / JWT ---
    JWT_SECRET: str
    JWT_ALG: str = Field(default="HS256")
    # Время жизни токенов в секундах.
    ACCESS_TTL: int = Field(default=15 * 60)
    REFRESH_TTL: int = Field(default=30 * 24 * 60 * 60)
    JWT_ISS: str = Field(default="saviorbill")

    # Ключ для симметричного шифрования секретов в БД (Fernet, urlsafe base64).
    # Если не задан — секреты OAuth-провайдеров хранятся как есть (dev-режим).
    SECRETS_KEY: str | None = Field(default=None)

    # --- OAuth ---
    # Базовый публичный URL ядра, на который провайдеры возвращают redirect.
    PUBLIC_URL: str = Field(default="http://localhost:8000")

    # --- Монтируемая папка данных (lua-скрипты, ключи, загрузки) ---
    DATA_DIR: str = Field(default="data")
    # Папка lua-скриптов. Если не задана явно — DATA_DIR/lua.
    LUA_SCRIPTS_DIR: str | None = Field(default=None)

    # --- LuaWorker (шина Redis Streams) ---
    LUA_TASK_STREAM: str = Field(default="lua:tasks")
    LUA_RESP_STREAM: str = Field(default="lua:results")
    LUA_GROUP: str = Field(default="luaworkers")
    # Таймаут ожидания ответа от LuaWorker, секунды.
    LUA_CALL_TIMEOUT: int = Field(default=30)
    # Сервисный токен, которым LuaWorker дёргает внутренние команды биллинга.
    LUA_SERVICE_TOKEN: str | None = Field(default=None)

    # --- Хранилище файлов (медиа товаров, аватарки, иконки) ---
    # fs — локальная ФС (UPLOADS_DIR); s3 — S3-совместимое хранилище.
    STORAGE_BACKEND: str = Field(default="fs")
    S3_ENDPOINT: str | None = Field(default=None)
    S3_BUCKET: str | None = Field(default=None)
    S3_REGION: str | None = Field(default=None)
    S3_KEY: str | None = Field(default=None)
    S3_SECRET: str | None = Field(default=None)
    # Публичный базовый URL для отдачи файлов (CDN/бакет).
    S3_PUBLIC_URL: str | None = Field(default=None)

    # --- SMTP (сидится в таблицу settings при первом запуске) ---
    SMTP_HOST: str | None = Field(default=None)
    SMTP_PORT: int = Field(default=587)
    SMTP_USER: str | None = Field(default=None)
    SMTP_PASS: str | None = Field(default=None)
    SMTP_FROM: str | None = Field(default=None)
    SMTP_TLS: bool = Field(default=True)

    # --- Bootstrap owner (создаётся при первом запуске системы) ---
    OWNER_LOGIN: str | None = Field(default=None)
    OWNER_PASS: str | None = Field(default=None)
    OWNER_EMAIL: str | None = Field(default=None)

    model_config = SettingsConfigDict(
        env_file=(".env", ".env.dev"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def _resolve_paths(self) -> "AppConfig":
        """Достроить путь к lua-скриптам из DATA_DIR, если он не задан явно."""
        if not self.LUA_SCRIPTS_DIR:
            self.LUA_SCRIPTS_DIR = str(Path(self.DATA_DIR) / "lua")
        return self

    @property
    def data_path(self) -> Path:
        """Корень монтируемой папки данных."""
        return Path(self.DATA_DIR)

    @property
    def keys_dir(self) -> Path:
        """Папка для ключей шифрования (создаётся при необходимости)."""
        return self.data_path / "keys"

    @property
    def uploads_dir(self) -> Path:
        """Папка для загружаемых файлов (бэкенд fs)."""
        return self.data_path / "uploads"

    @property
    def secret_key_file(self) -> Path:
        """Файл с автогенерируемым ключом шифрования секретов."""
        return self.keys_dir / "secret.key"

    @property
    def db_url(self) -> URL:
        """URL для подключения к БД"""
        return URL.create(
            drivername=self.DB_DRIVER,
            username=self.DB_USER,
            password=self.DB_PASS,
            host=self.DB_HOST,
            port=self.DB_PORT,
            database=self.DB_NAME
        )

    @property
    def valkey_url(self) -> str:
        """URL для подключения к Valkey"""
        return f"redis://{self.VALKEY_HOST}:{self.VALKEY_PORT}/{self.VALKEY_DB}"