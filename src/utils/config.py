from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from sqlalchemy.engine.url import URL

from utils.version import resolve_app_version

# Корень приложения: в Docker-образе — /app (VERSION лежит рядом), в
# локальном чек-ауте — корень репозитория (.git лежит рядом). Этот файл —
# src/utils/config.py, поэтому корень — на два уровня выше src/.
_BASE_DIR = Path(__file__).resolve().parents[2]

APP_NAME = os.environ.get("APP_NAME", "SaviorBill")
APP_VERSION = resolve_app_version(_BASE_DIR)


class AppConfig(BaseSettings):
    """Конфигурация приложения (постоянные ENV (настройки) + разовые seed4settings)."""

    # Настройки

    # Приложение
    HOST: str = Field(default="0.0.0.0")
    PORT: int = Field(default=8000)
    DEBUG: bool = Field(default=False)
    DOCS_ENABLED: bool = Field(default=True)

    # Публичные домены проекта
    DOMAIN: str | None = Field(default=None)
    MEDIA_DOMAIN: str | None = Field(default=None)

    # Публичный URL (редиректы OAuth, ссылки в письмах и т.п)
    PUBLIC_URL: str = Field(default="http://localhost:8000")
    MEDIA_PUBLIC_URL: str | None = Field(default=None)

    # URL сервиса mediaworker (внутренняя сеть) для служебных обращений billing.
    MEDIAWORKER_URL: str = Field(default="http://mediaworker:8001")

    # БД
    DB_DRIVER: str = Field(default="postgresql+asyncpg")
    DB_USER: str = Field(default="saviorbill")
    DB_PASS: str | None = Field(default=None)
    DB_PASS_FILE: str | None = Field(default=None)
    DB_HOST: str = Field(default="localhost")
    DB_PORT: int = Field(default=5432)
    DB_NAME: str = Field(default="saviorbill")

    # Valkey / Redis
    VALKEY_HOST: str = Field(default="localhost")
    VALKEY_PORT: int = Field(default=6379)
    VALKEY_DB: int = Field(default=0)

    # Auth / JWT
    JWT_SECRET: str | None = Field(default=None)
    JWT_SECRET_FILE: str | None = Field(default=None)
    JWT_ALG: str = Field(default="HS256")
    ACCESS_TOKEN_TTL: int = Field(default=15 * 60)
    REFRESH_TOKEN_TTL: int = Field(default=30 * 24 * 60 * 60)
    JWT_ISS: str = Field(default="saviorbill")

    # Шифрование секретов (SecBox / Fernet)
    SECRETS_KEY: str | None = Field(default=None)
    SECRETS_KEY_PATH: str | None = Field(default=None)

    # Бэкенд секретов (file|aws|gcp|azure|vault)
    SECRETS_BACKEND: str = Field(default="file")
    SECRETS_PREFIX: str = Field(default="saviorbill/")
    # Облачные координаты (нужны только для соответствующего бэкенда).
    SECRETS_AWS_REGION: str | None = Field(default=None)
    SECRETS_GCP_PROJECT: str | None = Field(default=None)
    SECRETS_AZURE_VAULT_URL: str | None = Field(default=None)
    SECRETS_VAULT_ADDR: str | None = Field(default=None)
    SECRETS_VAULT_TOKEN: str | None = Field(default=None)
    SECRETS_VAULT_MOUNT: str = Field(default="secret")



    # Монтируемая папка данных (lua-скрипты, ключи, загрузки)
    DATA_DIR: str = Field(default="data")
    # Папка lua-скриптов. Если не задана явно - DATA_DIR/lua.
    LUA_SCRIPTS_DIR: str | None = Field(default=None)
    # Папка email-шаблонов (jinja2). Если не задана явно - DATA_DIR/email.
    EMAIL_TEMPLATES_DIR: str | None = Field(default=None)

    # LuaWorker (шина Redis Streams)
    LUA_TASK_STREAM: str = Field(default="lua:tasks")
    LUA_RESP_STREAM: str = Field(default="lua:results")
    LUA_GROUP: str = Field(default="luaworkers")
    LUA_CALL_TIMEOUT: int = Field(default=30)
    # Сервисный токен LuaWorker - генерируемый секрет (файл LUA_SERVICE_TOKEN_FILE
    # по умолчанию либо облачный менеджер).
    LUA_SERVICE_TOKEN: str | None = Field(default=None)
    LUA_SERVICE_TOKEN_FILE: str | None = Field(default=None)

    # Billing-loop (планировщик истечений услуг и перепроверок платежей)
    BILLING_LOOP_ENABLED: bool = Field(default=True)
    # Размер «окна» очереди: сколько ближайших задач держать наготове.
    BILLING_QUEUE_WINDOW: int = Field(default=100)
    # Максимальная пауза сна планировщика (сек), даже если ближайшая задача далеко.
    BILLING_IDLE_SECONDS: int = Field(default=30)
    # Через сколько секунд «висящего» pending-платежа ставить перепроверку.
    BILLING_PAY_RECHECK_AFTER: int = Field(default=900)
    # Интервал авто-перепроверок платежа (сек) и их предел до статуса wait.
    BILLING_PAY_RECHECK_INTERVAL: int = Field(default=300)
    BILLING_PAY_RECHECK_MAX: int = Field(default=5)
    # Ключи Valkey для очереди задач и распределённого лока планировщика.
    BILLING_QUEUE_KEY: str = Field(default="billing:queue")
    BILLING_ATTEMPTS_KEY: str = Field(default="billing:pay_attempts")
    # DEPRECATED: распределённый лок больше не используется — очередь разделяемая,
    # задачи выбираются атомарным claim (ZRANGEBYSCORE+ZREM). Поля оставлены для
    # обратной совместимости конфигов и будут удалены в будущем.
    BILLING_LOCK_KEY: str = Field(default="billing:lock")
    # DEPRECATED: TTL неиспользуемого лока планировщика (сек).
    BILLING_LOCK_TTL: int = Field(default=30)
    # Предел одновременно обрабатываемых задач за одну итерацию (backpressure).
    BILLING_CONCURRENCY: int = Field(default=4)
    # Dead-letter очередь и предел попыток исполнения задачи биллинга.
    BILLING_QUEUE_DLQ: str = Field(default="billing:queue:dead")
    BILLING_QUEUE_MAX_ATTEMPTS: int = Field(default=5)

    # Реферальная программа: глобальный процент отчислений рефереру (%).
    REFERRAL_PERCENT: int = Field(default=0)

    # Хранилище файлов (медиа товаров, аватарки, иконки)
    STORAGE_BACKEND: str = Field(default="fs")
    S3_ENDPOINT: str | None = Field(default=None)
    S3_BUCKET: str | None = Field(default=None)
    S3_REGION: str | None = Field(default=None)
    S3_KEY: str | None = Field(default=None)
    S3_SECRET: str | None = Field(default=None)
    S3_SECRET_FILE: str | None = Field(default=None)
    S3_PUBLIC_URL: str | None = Field(default=None)

    # Кэш / TTL / лимиты (дехардкод)
    SETTINGS_CACHE_TTL: int = Field(default=300)
    # TTL кода подтверждения email и сброса пароля (сидится в settings как
    # mail.code_ttl, далее берётся из БД).
    VERIFY_TOKEN_TTL: int = Field(default=3600)
    OAUTH_STATE_TTL: int = Field(default=600)
    # Лимит строк в самоочищающихся таблицах (логи).
    LOG_ROW_LIMIT: int = Field(default=1_000_000)

    # Загрузка медиа
    # Порог «маленького» файла (аватарки/иконки): до него хватает media.upload,
    # выше - нужно право media.uploadlarge.
    MEDIA_SMALL_MAX_BYTES: int = Field(default=1_048_576)  # 1 MiB
    # Жёсткий потолок размера любого загружаемого файла.
    MEDIA_MAX_BYTES: int = Field(default=524_288_000)  # 500 MiB (media.uploadlarge)
    # Стрим задач медиа (конвертация/удаление) в Valkey.
    MEDIA_TASK_STREAM: str = Field(default="media:tasks")
    # Стрим результатов конвертации: mediaworker публикует готовое медиа, billing
    # (владелец схемы БД) его потребляет и записывает. Consumer-группа шардирует
    # нагрузку между инстансами billing (каждый результат обрабатывается один раз).
    MEDIA_RESULT_STREAM: str = Field(default="media:results")
    MEDIA_RESULT_GROUP: str = Field(default="billingmedia")
    # TTL статуса конвертации в Valkey (сек).
    MEDIA_STATUS_TTL: int = Field(default=3600)
    # Бан IP при фейковом Content-Length (сек).
    MEDIA_BAN_SECONDS: int = Field(default=180)
    # Dead-letter очереди и пределы попыток для медиа-задач/результатов.
    MEDIA_TASK_DLQ: str = Field(default="media:tasks:dead")
    MEDIA_TASK_MAX_ATTEMPTS: int = Field(default=5)
    MEDIA_RESULT_DLQ: str = Field(default="media:results:dead")
    MEDIA_RESULT_MAX_ATTEMPTS: int = Field(default=5)

    # Rate limiting (Valkey, fixed window)
    RATE_LIMIT_ENABLED: bool = Field(default=True)
    RATE_LIMIT_DEFAULT_MAX: int = Field(default=60)
    RATE_LIMIT_DEFAULT_WINDOW: int = Field(default=60)
    # Вход/регистрация (анти-брутфорс).
    RATE_LIMIT_AUTH_MAX: int = Field(default=10)
    RATE_LIMIT_AUTH_WINDOW: int = Field(default=60)
    # Запрос писем верификации/сброса (анти-спам).
    RATE_LIMIT_MAIL_MAX: int = Field(default=3)
    RATE_LIMIT_MAIL_WINDOW: int = Field(default=3600)
    # Чувствительные действия (покупки, активация промокодов, выдачи).
    RATE_LIMIT_SENSITIVE_MAX: int = Field(default=20)
    RATE_LIMIT_SENSITIVE_WINDOW: int = Field(default=60)

    # Доверенные reverse-proxy (CSV IP/CIDR). По умолчанию пусто — X-Forwarded-For
    # полностью игнорируется, идентификатор клиента для rate-limit — только
    # `request.client.host` (реальный TCP-peer). Если задано — ASGI-миддлварь
    # уровня Starlette подменяет client host на адрес из X-Forwarded-For, но
    # **только** когда непосредственный peer входит в этот список (иначе подмена
    # заголовка клиентом напрямую не даёт обойти лимит).
    TRUSTED_PROXIES: str = Field(default="")

    # Разрешённые CORS origin'ы (CSV, например "https://admin.example.com, https://app.example.com").
    # Пусто по умолчанию -> CORSMiddleware не
    # подключается вовсе (поведение как раньше: без явных CORS-заголовков).
    # Нужно, если admin/client UI обращается к billing с другого домена/порта
    # через fetch()/XHR (не требуется для простой отдачи `<img>`/`<video>`).
    CORS_ORIGINS: str = Field(default="")

    # Наблюдаемость: метрики Prometheus (/metrics) и трейсинг OpenTelemetry.
    # Метрики: эндпоинт /metrics включён по умолчанию (METRICS_ENABLED=false — снят).
    METRICS_ENABLED: bool = Field(default=True)
    # Токен для доступа к /metrics (заголовок X-Metrics-Token). Основная защита —
    # сетевая (реверс-прокси не проксирует /metrics наружу, см. deploy/Caddyfile);
    # токен — дополнительный рубеж на случай прямого доступа к порту контейнера.
    # Если не задан — эндпоинт не защищён токеном (полагаемся только на сеть).
    METRICS_TOKEN: str | None = Field(default=None)
    # Трейсинг OpenTelemetry. Выключен по умолчанию: включается флагом и требует
    # заданного OTLP-эндпоинта коллектора/Jaeger. Когда выключен — нулевой оверхед
    # (провайдер не ставится, инструментация не применяется).
    OTEL_ENABLED: bool = Field(default=False)
    # OTLP-эндпоинт коллектора (например, Jaeger): grpc — host:4317, http — :4318.
    OTEL_EXPORTER_OTLP_ENDPOINT: str | None = Field(default=None)
    # Протокол экспорта спанов: grpc (по умолчанию) либо http/protobuf.
    OTEL_EXPORTER_OTLP_PROTOCOL: str = Field(default="grpc")
    # Плейнтекст (без TLS) для grpc-экспорта — по умолчанию true, т.к. коллектор/Jaeger
    # обычно живёт во внутренней сети без TLS. В проде с TLS-коллектором — false.
    OTEL_EXPORTER_OTLP_INSECURE: bool = Field(default=True)
    # Имя сервиса в трейсах (по умолчанию — имя приложения).
    OTEL_SERVICE_NAME: str | None = Field(default=None)

    # РАЗОВЫЕ ENV (seed -> settings)

    # SMTP (сидится в settings при первом запуске)
    SMTP_HOST: str | None = Field(default=None)
    SMTP_PORT: int = Field(default=587)
    SMTP_USER: str | None = Field(default=None)
    SMTP_PASS: str | None = Field(default=None)
    SMTP_PASS_FILE: str | None = Field(default=None)
    SMTP_FROM: str | None = Field(default=None)
    SMTP_TLS: bool = Field(default=True)

    # Имена базовых ролей (сидятся в settings, далее берутся из БД)
    ROLE_OWNER: str = Field(default="owner")
    ROLE_ADMIN: str = Field(default="admin")
    ROLE_MANAGER: str = Field(default="manager")
    ROLE_SUPPORT: str = Field(default="support")
    ROLE_MEDIA: str = Field(default="media")
    # Роль обычного (верифицированного) пользователя.
    ROLE_USER: str = Field(default="user")
    # Роль только что зарегистрированного пользователя (email не подтверждён).
    ROLE_GUEST: str = Field(default="guest")
    # Роль заблокированного пользователя (только просмотр своего профиля/услуг).
    ROLE_BANNED: str = Field(default="banned")

    # Bootstrap owner (создаётся при первом запуске)
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
        if not self.JWT_SECRET_FILE:
            self.JWT_SECRET_FILE = str(Path(self.DATA_DIR) / "keys" / "jwt.key")
        if not self.LUA_SERVICE_TOKEN_FILE:
            self.LUA_SERVICE_TOKEN_FILE = str(
                Path(self.DATA_DIR) / "keys" / "lua_service.token"
            )
        return self

    @property
    def trusted_proxies_list(self) -> list[str]:
        """`TRUSTED_PROXIES` как список непустых IP/CIDR (CSV → list)."""
        return [p.strip() for p in self.TRUSTED_PROXIES.split(",") if p.strip()]

    @property
    def cors_origins_list(self) -> list[str]:
        """`CORS_ORIGINS` как список непустых origin'ов (CSV → list)."""
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def media_docs_url(self) -> str:
        """Публичный URL OpenAPI-документации mediaworker.
        """
        base = self.MEDIA_PUBLIC_URL
        if not base:
            base = f"https://{self.MEDIA_DOMAIN}" if self.MEDIA_DOMAIN \
                else self.MEDIA_PUBLIC_URL if self.MEDIA_PUBLIC_URL \
                else self.MEDIAWORKER_URL
        return f"{base.rstrip('/')}/api/media/docs"

    @property
    def data_path(self) -> Path:
        """Корень монтируемой папки данных."""
        return Path(self.DATA_DIR)

    @property
    def keys_dir(self) -> Path:
        """Папка для ключей шифрования (создаётся при необходимости)."""
        return self.data_path / "keys"

    @property
    def instance_id(self) -> str:
        """Уникальный идентификатор процесса-инстанса (для имён консьюмеров).

        Используется как имя консьюмера в Valkey consumer-группах, чтобы при
        горизонтальном масштабировании инстансы не делили одно имя (иначе ломается
        учёт pending/claim). Стабилен в пределах процесса (hostname + pid).
        """
        import os
        import socket

        return f"{socket.gethostname()}-{os.getpid()}"

    @property
    def uploads_dir(self) -> Path:
        """Папка для загружаемых файлов (бэкенд fs)."""
        return self.data_path / "uploads"

    @property
    def media_dir(self) -> Path:
        """Публичная папка готовых медиа (отдаёт Caddy), бэкенд fs."""
        return self.data_path / "media"

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
