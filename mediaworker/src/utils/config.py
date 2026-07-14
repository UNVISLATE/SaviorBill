"""Конфигурация mediaworker (pydantic_settings, тот же .env что у billing).

Читает переменные окружения через pydantic_settings. Все имена переменных
совпадают с billing-конфигом — один .env файл на весь стек.
"""

from __future__ import annotations

import os
import socket
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_consumer() -> str:
    """Уникальное имя консьюмера на инстанс (hostname-pid)."""
    return f"{socket.gethostname()}-{os.getpid()}"


class Config(BaseSettings):
    """Настройки процесса mediaworker."""

    # --- HTTP-сервер ---
    MEDIA_HOST: str = Field(default="0.0.0.0")
    MEDIA_PORT: int = Field(default=8001)

    # --- Valkey / Redis ---
    VALKEY_HOST: str = Field(default="valkey")
    VALKEY_PORT: int = Field(default=6379)
    VALKEY_DB: int = Field(default=0)

    # --- Папка данных ---
    DATA_DIR: str = Field(default="/app/data")

    # --- PostgreSQL (только SELECT — схемой владеет billing) ---
    DB_USER: str = Field(default="saviorbill")
    DB_PASS: str | None = Field(default=None)
    DB_PASS_FILE: str | None = Field(default=None)
    DB_HOST: str = Field(default="db")
    DB_PORT: int = Field(default=5432)
    DB_NAME: str = Field(default="saviorbill")
    # Явный DSN — переопределяет сборку из DB_* (необязателен).
    DB_DSN: str | None = Field(default=None)

    # --- JWT (общий секрет с billing) ---
    JWT_SECRET: str | None = Field(default=None)
    JWT_SECRET_FILE: str | None = Field(default=None)
    JWT_ALG: str = Field(default="HS256")
    JWT_ISS: str = Field(default="saviorbill")

    # --- Медиа-стримы Valkey ---
    MEDIA_TASK_STREAM: str = Field(default="media:tasks")
    MEDIA_RESULT_STREAM: str = Field(default="media:results")
    MEDIA_GROUP: str = Field(default="mediaworkers")
    MEDIA_CONSUMER: str = Field(default_factory=_default_consumer)
    # Приблизительный потолок длины стримов (XADD ... MAXLEN ~ N) — без него
    # Valkey Streams растут неограниченно (xack не удаляет записи физически).
    MEDIA_TASK_STREAM_MAXLEN: int = Field(default=10_000)
    MEDIA_RESULT_STREAM_MAXLEN: int = Field(default=10_000)

    # --- Журнал тасков (наблюдаемость, независима от OTEL) ---
    # Кольцевой буфер записей на kind ("media") + TTL всего списка.
    MEDIA_TASKLOG_MAXLEN: int = Field(default=500)
    MEDIA_TASKLOG_TTL: int = Field(default=604_800)  # 7 дней

    # --- Realtime-лог сырого вывода ffmpeg/ffprobe (xterm.js в админке) ---
    # Сколько последних запусков (job_id) хранить в списке "недавние" и TTL
    # на метаданные/строки каждого запуска (короткий — это debug-инструмент,
    # не журнал фактов).
    MEDIA_PROCLOG_MAX_JOBS: int = Field(default=50)
    MEDIA_PROCLOG_TTL: int = Field(default=3600)  # 1 час

    # --- Квоты и лимиты ---
    MEDIA_STATUS_TTL: int = Field(default=3600)
    MEDIA_BAN_SECONDS: int = Field(default=180)
    MEDIA_KEEP_ORIGINAL: bool = Field(default=False)
    MEDIA_MAX_BYTES: int = Field(default=524_288_000)  # 500 MiB (media.uploadlarge)
    MEDIA_SMALL_MAX_BYTES: int = Field(default=1_048_576)  # 1 MiB
    MEDIA_UPLOADS_PER_HOUR: int = Field(default=30)

    # --- Параметры конвертации ---
    MEDIA_WEBP_QUALITY: int = Field(default=82)
    MEDIA_WEBM_CRF: int = Field(default=33)
    MEDIA_THUMB_SIZE: int = Field(default=96)
    MEDIA_THUMB_QUALITY: int = Field(default=40)

    # --- Двухшаговая загрузка ---
    MEDIA_UPLOAD_TOKEN_TTL: int = Field(default=60)

    # --- Backpressure и надёжность ---
    MEDIA_TASK_CONCURRENCY: int = Field(default=4)
    MEDIA_TASK_MAX_ATTEMPTS: int = Field(default=5)
    MEDIA_TASK_DLQ: str = Field(default="media:tasks:dead")

    # --- OpenAPI ---
    MEDIA_DOCS_ENABLED: bool = Field(default=True)

    # --- Хранилище ---
    STORAGE_BACKEND: str = Field(default="fs")
    S3_ENDPOINT: str | None = Field(default=None)
    S3_BUCKET: str | None = Field(default=None)
    S3_REGION: str | None = Field(default=None)
    S3_KEY: str | None = Field(default=None)
    S3_SECRET: str | None = Field(default=None)

    # --- Роли ---
    ROLE_BANNED: str = Field(default="banned")

    # Разрешённые CORS origin'ы (CSV; общее имя переменной с billing —
    # значение можно переопределить отдельно, если mediaworker живёт на
    # другом наборе доменов). Пусто -> CORSMiddleware не подключается.
    CORS_ORIGINS: str = Field(default="")

    # --- Наблюдаемость: метрики Prometheus (/metrics) и трейсинг OpenTelemetry ---
    # Имена переменных совпадают с billing-конфигом (общий .env на весь стек).
    METRICS_ENABLED: bool = Field(default=True)
    METRICS_TOKEN: str | None = Field(default=None)
    OTEL_ENABLED: bool = Field(default=False)
    OTEL_EXPORTER_OTLP_ENDPOINT: str | None = Field(default=None)
    OTEL_EXPORTER_OTLP_PROTOCOL: str = Field(default="grpc")
    OTEL_EXPORTER_OTLP_INSECURE: bool = Field(default=True)
    OTEL_SERVICE_NAME: str | None = Field(default=None)

    model_config = SettingsConfigDict(
        env_file=(".env", ".env.dev"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def _resolve_defaults(self) -> "Config":
        """Достроить пути из DATA_DIR, если не заданы явно."""
        if not self.JWT_SECRET_FILE:
            self.JWT_SECRET_FILE = str(Path(self.DATA_DIR) / "keys" / "jwt.key")
        return self

    # ------------------------------------------------------------------ #
    # Вычисляемые свойства (совпадают с атрибутами старого Config).       #
    # ------------------------------------------------------------------ #

    @property
    def valkey_url(self) -> str:
        return f"redis://{self.VALKEY_HOST}:{self.VALKEY_PORT}/{self.VALKEY_DB}"

    @property
    def db_dsn(self) -> str:
        """DSN для asyncpg."""
        if self.DB_DSN:
            return self.DB_DSN
        return (
            f"postgresql://{self.DB_USER}:{self._db_pass()}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    def _db_pass(self) -> str:
        if self.DB_PASS:
            return self.DB_PASS
        fp = self.DB_PASS_FILE or str(Path(self.DATA_DIR) / "keys" / "db.pass")
        if fp and os.path.exists(fp):
            return Path(fp).read_text(encoding="utf-8").strip()
        return ""

    @property
    def uploads_dir(self) -> str:
        return str(Path(self.DATA_DIR) / "uploads")

    @property
    def media_dir(self) -> str:
        return str(Path(self.DATA_DIR) / "media")

    def resolve_jwt_secret(self) -> str:
        """Актуальный JWT-секрет: ENV, иначе — свежее чтение файла ключа."""
        if self.JWT_SECRET:
            return self.JWT_SECRET
        if self.JWT_SECRET_FILE and os.path.exists(self.JWT_SECRET_FILE):
            return Path(self.JWT_SECRET_FILE).read_text(encoding="utf-8").strip()
        return ""

    # --- Алиасы для совместимости с кодом, использующим старые имена ---

    @property
    def task_stream(self) -> str:
        return self.MEDIA_TASK_STREAM

    @property
    def result_stream(self) -> str:
        return self.MEDIA_RESULT_STREAM

    @property
    def group(self) -> str:
        return self.MEDIA_GROUP

    @property
    def consumer(self) -> str:
        return self.MEDIA_CONSUMER

    @property
    def status_ttl(self) -> int:
        return self.MEDIA_STATUS_TTL

    @property
    def ban_seconds(self) -> int:
        return self.MEDIA_BAN_SECONDS

    @property
    def keep_original(self) -> bool:
        return self.MEDIA_KEEP_ORIGINAL

    @property
    def max_bytes(self) -> int:
        return self.MEDIA_MAX_BYTES

    @property
    def small_max_bytes(self) -> int:
        return self.MEDIA_SMALL_MAX_BYTES

    @property
    def uploads_per_hour(self) -> int:
        return self.MEDIA_UPLOADS_PER_HOUR

    @property
    def webp_quality(self) -> int:
        return self.MEDIA_WEBP_QUALITY

    @property
    def webm_crf(self) -> int:
        return self.MEDIA_WEBM_CRF

    @property
    def thumb_size(self) -> int:
        return self.MEDIA_THUMB_SIZE

    @property
    def thumb_quality(self) -> int:
        return self.MEDIA_THUMB_QUALITY

    @property
    def upload_token_ttl(self) -> int:
        return self.MEDIA_UPLOAD_TOKEN_TTL

    @property
    def task_concurrency(self) -> int:
        return self.MEDIA_TASK_CONCURRENCY

    @property
    def task_max_attempts(self) -> int:
        return self.MEDIA_TASK_MAX_ATTEMPTS

    @property
    def task_dlq_stream(self) -> str:
        return self.MEDIA_TASK_DLQ

    @property
    def task_stream_maxlen(self) -> int:
        return self.MEDIA_TASK_STREAM_MAXLEN

    @property
    def result_stream_maxlen(self) -> int:
        return self.MEDIA_RESULT_STREAM_MAXLEN

    @property
    def tasklog_maxlen(self) -> int:
        return self.MEDIA_TASKLOG_MAXLEN

    @property
    def tasklog_ttl(self) -> int:
        return self.MEDIA_TASKLOG_TTL

    @property
    def proclog_max_jobs(self) -> int:
        return self.MEDIA_PROCLOG_MAX_JOBS

    @property
    def proclog_ttl(self) -> int:
        return self.MEDIA_PROCLOG_TTL

    @property
    def backend(self) -> str:
        return self.STORAGE_BACKEND.lower()

    @property
    def role_banned(self) -> str:
        return self.ROLE_BANNED

    @property
    def docs_enabled(self) -> bool:
        return self.MEDIA_DOCS_ENABLED

    @property
    def cors_origins_list(self) -> list[str]:
        """`CORS_ORIGINS` как список непустых origin'ов (CSV → list)."""
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def jwt_alg(self) -> str:
        return self.JWT_ALG

    @property
    def jwt_iss(self) -> str:
        return self.JWT_ISS

    @property
    def s3_endpoint(self) -> str | None:
        return self.S3_ENDPOINT

    @property
    def s3_bucket(self) -> str | None:
        return self.S3_BUCKET

    @property
    def s3_region(self) -> str | None:
        return self.S3_REGION

    @property
    def s3_key(self) -> str | None:
        return self.S3_KEY

    @property
    def s3_secret(self) -> str | None:
        return self.S3_SECRET

    @classmethod
    def load(cls) -> "Config":
        """Обратная совместимость: старый factory-метод."""
        return cls()


__all__ = ["Config"]
