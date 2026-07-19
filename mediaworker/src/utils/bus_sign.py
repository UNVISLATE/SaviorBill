"""HMAC-подпись сообщений в общей шине Valkey Streams (mediaworker-сторона).

Зеркало ``billing/src/security/sec/bus_sign.py`` — продублировано по значению
(не импортом), т.к. mediaworker и billing — отдельные деплойменты без общего
пакета Python. При правке синхронизировать оба файла (см. AUDIT.md H1).
"""

from __future__ import annotations

import hashlib
import hmac
import time

DEFAULT_MAX_SKEW_SEC = 300


def _canonical(fields: dict) -> bytes:
    """Каноническая строка полей (без ``sig``), отсортированных по имени."""
    items = sorted((str(k), str(v)) for k, v in fields.items() if k != "sig")
    return "\x1f".join(f"{k}={v}" for k, v in items).encode("utf-8")


def sign_fields(key: str, fields: dict) -> dict:
    """Вернуть копию ``fields`` с добавленными ``ts``+``sig`` (или без изменений, если ``key`` пуст)."""
    if not key:
        return dict(fields)
    body = dict(fields)
    body["ts"] = str(int(time.time()))
    body["sig"] = hmac.new(key.encode("utf-8"), _canonical(body), hashlib.sha256).hexdigest()
    return body


def verify_fields(
    key: str, fields: dict, max_skew: int = DEFAULT_MAX_SKEW_SEC
) -> bool:
    """Проверить подпись и окно времени сообщения шины (``True``, если ``key`` пуст)."""
    if not key:
        return True
    sig = fields.get("sig")
    ts = fields.get("ts")
    if not sig or not ts:
        return False
    try:
        skew = abs(time.time() - float(ts))
    except (TypeError, ValueError):
        return False
    if skew > max_skew:
        return False
    body = {k: v for k, v in fields.items() if k != "sig"}
    expected = hmac.new(key.encode("utf-8"), _canonical(body), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, str(sig))


__all__ = ["sign_fields", "verify_fields", "DEFAULT_MAX_SKEW_SEC"]
