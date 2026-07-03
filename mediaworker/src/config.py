"""Конфигурация mediaworker (из ENV).

mediaworker самодостаточен: работает с Postgres напрямую (валидация access-JWT,
чтение роли/квоты, запись готового медиа), Valkey (очередь/статусы/бан/лимиты) и
хранилищем (файловая система / S3). О биллинге сервис ничего не знает.
"""

from __future__ import annotations

import os
import socket
from dataclasses import dataclass
from pathlib import Path


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _read_secret(value: str | None, file_env: str, default_path: str | None) -> str:
    """Значение секрета: приоритет ENV, затем файл (``*_FILE`` или дефолтный путь)."""
    if value:
        return value
    path = os.getenv(file_env) or default_path
    if path and os.path.exists(path):
        return Path(path).read_text(encoding="utf-8").strip()
    return ""


@dataclass(slots=True)
class Config:
    """Настройки процесса mediaworker."""

    valkey_url: str
    data_dir: str
    uploads_dir: str
    media_dir: str

    # Postgres (asyncpg DSN).
    db_dsn: str

    # Проверка access-JWT (общий секрет с billing).
    jwt_secret: str
    jwt_secret_file: str | None
    jwt_alg: str
    jwt_iss: str

    task_stream: str
    result_stream: str
    group: str
    consumer: str

    status_ttl: int
    ban_seconds: int
    keep_original: bool

    # TTL одноразового upload-token (двухшаговая загрузка), сек.
    upload_token_ttl: int
    # Повторы обработки медиа-задач воркером и dead-letter стрим.
    task_max_attempts: int
    task_dlq_stream: str
    # Предел одновременно обрабатываемых задач (backpressure).
    task_concurrency: int

    # Квоты и лимиты загрузок.
    max_bytes: int
    small_max_bytes: int
    uploads_per_hour: int
    role_banned: str

    backend: str  # fs | s3
    s3_endpoint: str | None
    s3_bucket: str | None
    s3_region: str | None
    s3_key: str | None
    s3_secret: str | None

    webp_quality: int
    webm_crf: int
    thumb_size: int
    thumb_quality: int

    # OpenAPI-документация (Swagger UI/ReDoc/openapi.json). По умолчанию включена.
    docs_enabled: bool

    @classmethod
    def load(cls) -> "Config":
        """Собрать конфигурацию из переменных окружения."""
        host = os.getenv("VALKEY_HOST", "valkey")
        port = os.getenv("VALKEY_PORT", "6379")
        db = os.getenv("VALKEY_DB", "0")
        data_dir = os.getenv("DATA_DIR", "/app/data")
        # Уникальное имя консьюмера на инстанс: иначе несколько реплик mediaworker
        # делят одно имя в consumer-группе и ломают учёт pending/claim.
        default_consumer = f"{socket.gethostname()}-{os.getpid()}"

        db_pass = _read_secret(
            os.getenv("DB_PASS"),
            "DB_PASS_FILE",
            str(Path(data_dir) / "keys" / "db.pass"),
        )
        db_dsn = os.getenv("DB_DSN") or (
            f"postgresql://{os.getenv('DB_USER', 'aiosupport')}:{db_pass}"
            f"@{os.getenv('DB_HOST', 'db')}:{os.getenv('DB_PORT', '5432')}"
            f"/{os.getenv('DB_NAME', 'aiosupport')}"
        )
        jwt_secret = _read_secret(
            os.getenv("JWT_SECRET"),
            "JWT_SECRET_FILE",
            str(Path(data_dir) / "keys" / "jwt.key"),
        )
        jwt_secret_file = os.getenv("JWT_SECRET_FILE") or str(
            Path(data_dir) / "keys" / "jwt.key"
        )

        return cls(
            valkey_url=os.getenv("VALKEY_URL", f"redis://{host}:{port}/{db}"),
            data_dir=data_dir,
            uploads_dir=os.getenv("UPLOADS_DIR", os.path.join(data_dir, "uploads")),
            media_dir=os.getenv("MEDIA_DIR", os.path.join(data_dir, "media")),
            db_dsn=db_dsn,
            jwt_secret=jwt_secret,
            jwt_secret_file=jwt_secret_file,
            jwt_alg=os.getenv("JWT_ALG", "HS256"),
            jwt_iss=os.getenv("JWT_ISS", "saviorbill"),
            task_stream=os.getenv("MEDIA_TASK_STREAM", "media:tasks"),
            result_stream=os.getenv("MEDIA_RESULT_STREAM", "media:results"),
            group=os.getenv("MEDIA_GROUP", "mediaworkers"),
            consumer=os.getenv("MEDIA_CONSUMER", default_consumer),
            status_ttl=_int("MEDIA_STATUS_TTL", 3600),
            ban_seconds=_int("MEDIA_BAN_SECONDS", 180),
            keep_original=os.getenv("MEDIA_KEEP_ORIGINAL", "false").lower() == "true",
            upload_token_ttl=_int("MEDIA_UPLOAD_TOKEN_TTL", 60),
            task_max_attempts=_int("MEDIA_TASK_MAX_ATTEMPTS", 5),
            task_dlq_stream=os.getenv("MEDIA_TASK_DLQ", "media:tasks:dead"),
            task_concurrency=_int("MEDIA_TASK_CONCURRENCY", 4),
            max_bytes=_int("MEDIA_MAX_BYTES", 52_428_800),
            small_max_bytes=_int("MEDIA_SMALL_MAX_BYTES", 1_048_576),
            uploads_per_hour=_int("MEDIA_UPLOADS_PER_HOUR", 30),
            role_banned=os.getenv("ROLE_BANNED", "banned"),
            backend=os.getenv("STORAGE_BACKEND", "fs").lower(),
            s3_endpoint=os.getenv("S3_ENDPOINT"),
            s3_bucket=os.getenv("S3_BUCKET"),
            s3_region=os.getenv("S3_REGION"),
            s3_key=os.getenv("S3_KEY"),
            s3_secret=os.getenv("S3_SECRET"),
            webp_quality=_int("MEDIA_WEBP_QUALITY", 82),
            webm_crf=_int("MEDIA_WEBM_CRF", 33),
            thumb_size=_int("MEDIA_THUMB_SIZE", 96),
            thumb_quality=_int("MEDIA_THUMB_QUALITY", 40),
            docs_enabled=os.getenv("MEDIA_DOCS_ENABLED", "true").lower() == "true",
        )

    def resolve_jwt_secret(self) -> str:
        """Актуальный JWT-секрет: ENV, иначе — свежее чтение файла ключа.

        Файл ключа может быть создан billing уже после старта воркера, поэтому
        при пустом ENV читаем его на каждом запросе (значение кэширует ОС).
        """
        if self.jwt_secret:
            return self.jwt_secret
        if self.jwt_secret_file and os.path.exists(self.jwt_secret_file):
            return Path(self.jwt_secret_file).read_text(encoding="utf-8").strip()
        return ""


__all__ = ["Config"]
