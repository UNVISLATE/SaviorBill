"""Единый источник имён ключей Valkey для mediaworker."""

from __future__ import annotations

STATUS_PREFIX = "media:status:"
FILE_PREFIX = "media:file:"
OPSTATUS_PREFIX = "media:opstatus:"
UPTOKEN_PREFIX = "media:uptoken:"
RATE_PREFIX = "media:uprate:"


def status_key(token: str) -> str:
    """Статус основного медиа (``queued``/``processing``/``ready``/``failed``)."""
    return f"{STATUS_PREFIX}{token}"


def file_key(token: str) -> str:
    """Хэш вариантов (``main``/``thumb``/``preview.<uuid8>`` -> ключ файла)."""
    return f"{FILE_PREFIX}{token}"


def opstatus_key(token: str, op: str) -> str:
    """Статус побочной операции (``preview``/``thumb``) — не путать со ``status_key``."""
    return f"{OPSTATUS_PREFIX}{token}:{op}"


def uptoken_key(upload_token: str) -> str:
    """Одноразовый токен второго шага загрузки (``upload.py``)."""
    return f"{UPTOKEN_PREFIX}{upload_token}"


def rate_key(acc_id: int, bucket: int) -> str:
    """Счётчик часового лимита загрузок конкретного аккаунта."""
    return f"{RATE_PREFIX}{acc_id}:{bucket}"


__all__ = [
    "STATUS_PREFIX",
    "FILE_PREFIX",
    "OPSTATUS_PREFIX",
    "UPTOKEN_PREFIX",
    "RATE_PREFIX",
    "status_key",
    "file_key",
    "opstatus_key",
    "uptoken_key",
    "rate_key",
]
