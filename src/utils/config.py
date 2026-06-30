from __future__ import annotations

from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from sqlalchemy.engine.url import URL


class AppConfig(BaseSettings):
    """Конфигурация приложения (постоянные ENV + разовые seed → settings)."""

    # =========================== ПОСТОЯННЫЕ ENV ============================

    # --- Приложение ---
    APP_NAME: str = Field(default="SaviorBill")
    APP_VERSION: str = Field(default="0.0.1dev")
    HOST: str = Field(default="0.0.0.0")
    PORT: int = Field(default=8000)
    DEBUG: bool = Field(default=False)

    # --- БД ---
    DB_DRIVER: str = Field(default="postgresql+asyncpg")
    DB_USER: str = Field(default="aiosupport")
    DB_PASS: str
    DB_HOST: str = Field(default="localhost")
    DB_PORT: int = Field(default=5432)
    DB_NAME: str = Field(default="aiosupport")

    # --- Valkey / Redis ---
    VALKEY_HOST: str = Field(default="localhost")
    VALKEY_PORT: int = Field(default=6379)
    VALKEY_DB: int = Field(default=0)

    # --- Auth / JWT ---
    JWT_SECRET: str
    JWT_ALG: str = Field(default="HS256")
    ACCESS_TOKEN_TTL: int = Field(default=15 * 60)
    REFRESH_TOKEN_TTL: int = Field(default=30 * 24 * 60 * 60)
    JWT_ISS: str = Field(default="saviorbill")

    # --- Шифрование секретов (SecBox / Fernet) ---
    # SECRETS_KEY — сам ключ. Если не задан, при старте читается/создаётся в
    # файле SECRETS_KEY_PATH (см. lifespan + utils/init/secret.py).
    SECRETS_KEY: str | None = Field(default=None)
    SECRETS_KEY_PATH: str | None = Field(default=None)

    # --- Публичный URL (редиректы OAuth, ссылки в письмах) ---
    PUBLIC_URL: str = Field(default="http://localhost:8000")

    # --- Монтируемая папка данных (lua-скрипты, ключи, загрузки) ---
    DATA_DIR: str = Field(default="data")
    # Папка lua-скриптов. Если не задана явно — DATA_DIR/lua.
    LUA_SCRIPTS_DIR: str | None = Field(default=None)
    # Папка email-шаблонов (jinja2). Если не задана явно — DATA_DIR/email.
    EMAIL_TEMPLATES_DIR: str | None = Field(default=None)

    # --- LuaWorker (шина Redis Streams) ---
    LUA_TASK_STREAM: str = Field(default="lua:tasks")
    LUA_RESP_STREAM: str = Field(default="lua:results")
    LUA_GROUP: str = Field(default="luaworkers")
    LUA_CALL_TIMEOUT: int = Field(default=30)
    LUA_SERVICE_TOKEN: str | None = Field(default=None)

    # --- Хранилище файлов (медиа товаров, аватарки, иконки) ---
    STORAGE_BACKEND: str = Field(default="fs")
    S3_ENDPOINT: str | None = Field(default=None)
    S3_BUCKET: str | None = Field(default=None)
    S3_REGION: str | None = Field(default=None)
    S3_KEY: str | None = Field(default=None)
    S3_SECRET: str | None = Field(default=None)
    S3_PUBLIC_URL: str | None = Field(default=None)

    # --- Кэш / TTL / лимиты (дехардкод) ---
    SETTINGS_CACHE_TTL: int = Field(default=300)
    VERIFY_TOKEN_TTL: int = Field(default=3600)
    OAUTH_STATE_TTL: int = Field(default=600)
    RESET_TOKEN_TTL: int = Field(default=3600)
    # Лимит строк в самоочищающихся таблицах (логи).
    LOG_ROW_LIMIT: int = Field(default=1_000_000)

    # --- Загрузка медиа ---
    # Порог «маленького» файла (аватарки/иконки): до него хватает media.upload,
    # выше — нужно право media.uploadlarge.
    MEDIA_SMALL_MAX_BYTES: int = Field(default=1_048_576)  # 1 MiB
    # Жёсткий потолок размера любого загружаемого файла.
    MEDIA_MAX_BYTES: int = Field(default=52_428_800)  # 50 MiB

    # --- Rate limiting (Valkey, fixed window) ---
    RATE_LIMIT_ENABLED: bool = Field(default=True)
    RATE_LIMIT_DEFAULT_MAX: int = Field(default=60)
    RATE_LIMIT_DEFAULT_WINDOW: int = Field(default=60)
    # Вход/регистрация (анти-брутфорс).
    RATE_LIMIT_AUTH_MAX: int = Field(default=10)
    RATE_LIMIT_AUTH_WINDOW: int = Field(default=60)
    # Запрос писем верификации/сброса (анти-спам).
    RATE_LIMIT_MAIL_MAX: int = Field(default=3)
    RATE_LIMIT_MAIL_WINDOW: int = Field(default=3600)

    # ===================== РАЗОВЫЕ ENV (seed → settings) ==================

    # --- SMTP (сидится в settings при первом запуске) ---
    SMTP_HOST: str | None = Field(default=None)
    SMTP_PORT: int = Field(default=587)
    SMTP_USER: str | None = Field(default=None)
    SMTP_PASS: str | None = Field(default=None)
    SMTP_FROM: str | None = Field(default=None)
    SMTP_TLS: bool = Field(default=True)

    # --- Имена базовых ролей (сидятся в settings, далее берутся из БД) ---
    ROLE_OWNER: str = Field(default="owner")
    ROLE_ADMIN: str = Field(default="admin")
    ROLE_MANAGER: str = Field(default="manager")
    ROLE_SUPPORT: str = Field(default="support")
    # Роль обычного (верифицированного) пользователя.
    ROLE_USER: str = Field(default="user")
    # Роль заблокированного пользователя (только просмотр своего профиля/услуг).
    ROLE_BANNED: str = Field(default="banned")

    # --- Bootstrap owner (создаётся при первом запуске; НЕ хранится в settings) ---
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
        """Достроить пути из DATA_DIR, если не заданы явно."""
        if not self.LUA_SCRIPTS_DIR:
            self.LUA_SCRIPTS_DIR = str(Path(self.DATA_DIR) / "lua")
        if not self.EMAIL_TEMPLATES_DIR:
            self.EMAIL_TEMPLATES_DIR = str(Path(self.DATA_DIR) / "email")
        if not self.SECRETS_KEY_PATH:
            self.SECRETS_KEY_PATH = str(Path(self.DATA_DIR) / "keys" / "secret.key")
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
        return Path(self.SECRETS_KEY_PATH)

    @property
    def db_url(self) -> URL:
        """URL для подключения к БД."""
        return URL.create(
            drivername=self.DB_DRIVER,
            username=self.DB_USER,
            password=self.DB_PASS,
            host=self.DB_HOST,
            port=self.DB_PORT,
            database=self.DB_NAME,
        )

    @property
    def valkey_url(self) -> str:
        """URL для подключения к Valkey."""
        return f"redis://{self.VALKEY_HOST}:{self.VALKEY_PORT}/{self.VALKEY_DB}"
