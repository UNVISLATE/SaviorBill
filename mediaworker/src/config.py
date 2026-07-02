"""Конфигурация mediaworker (из ENV).

mediaworker не работает с Postgres — только Valkey, файловая система / S3 и
внутренний API billing (authorize/register). Все параметры берутся из окружения.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass(slots=True)
class Config:
    """Настройки процесса mediaworker."""

    valkey_url: str
    data_dir: str
    uploads_dir: str
    media_dir: str

    billing_url: str
    service_token: str

    task_stream: str
    group: str
    consumer: str

    status_ttl: int
    ban_seconds: int
    keep_original: bool

    backend: str  # fs | s3
    s3_endpoint: str | None
    s3_bucket: str | None
    s3_region: str | None
    s3_key: str | None
    s3_secret: str | None

    webp_quality: int
    webm_crf: int

    @classmethod
    def load(cls) -> "Config":
        """Собрать конфигурацию из переменных окружения."""
        host = os.getenv("VALKEY_HOST", "valkey")
        port = os.getenv("VALKEY_PORT", "6379")
        db = os.getenv("VALKEY_DB", "0")
        data_dir = os.getenv("DATA_DIR", "/app/data")
        return cls(
            valkey_url=os.getenv("VALKEY_URL", f"redis://{host}:{port}/{db}"),
            data_dir=data_dir,
            uploads_dir=os.getenv("UPLOADS_DIR", os.path.join(data_dir, "uploads")),
            media_dir=os.getenv("MEDIA_DIR", os.path.join(data_dir, "media")),
            billing_url=os.getenv("BILLING_URL", "http://billing:8000"),
            service_token=os.getenv("LUA_SERVICE_TOKEN", "dev-service-token"),
            task_stream=os.getenv("MEDIA_TASK_STREAM", "media:tasks"),
            group=os.getenv("MEDIA_GROUP", "mediaworkers"),
            consumer=os.getenv("MEDIA_CONSUMER", "media-1"),
            status_ttl=_int("MEDIA_STATUS_TTL", 3600),
            ban_seconds=_int("MEDIA_BAN_SECONDS", 180),
            keep_original=os.getenv("MEDIA_KEEP_ORIGINAL", "false").lower() == "true",
            backend=os.getenv("STORAGE_BACKEND", "fs").lower(),
            s3_endpoint=os.getenv("S3_ENDPOINT"),
            s3_bucket=os.getenv("S3_BUCKET"),
            s3_region=os.getenv("S3_REGION"),
            s3_key=os.getenv("S3_KEY"),
            s3_secret=os.getenv("S3_SECRET"),
            webp_quality=_int("MEDIA_WEBP_QUALITY", 82),
            webm_crf=_int("MEDIA_WEBM_CRF", 33),
        )


__all__ = ["Config"]
