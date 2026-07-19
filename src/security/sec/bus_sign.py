"""HMAC-подпись сообщений в общей шине Valkey Streams (billing/luaworker/mediaworker).

Без подписи любой процесс с доступом к тому же Valkey может
опубликовать поддельную задачу в ``lua:tasks``/``media:tasks`` или поддельный
результат в ``lua:results``/``media:results`` — раз ни билинг, ни воркеры
сейчас не проверяют происхождение сообщения, стрим де-факто trust-boundary
не является, хотя воркер выполняет код/деньги-операции по его содержимому.

Схема — общая для всех направлений (task/response, billing/lua/media):
подписывается каноническое представление ВСЕХ полей сообщения (кроме ``sig``),
отсортированных по имени поля, плюс метка времени ``ts`` (защита от replay —
сообщение с "протухшим" ``ts`` не проходит проверку). Секрет — общий
``BUS_SIGNING_KEY``, известный обеим сторонам шины (аналог общего
``JWT_SECRET`` между billing/mediaworker, но для другой цели — не спутывать).

Подпись отключена (``verify_fields`` всегда возвращает ``True``, ``sign_fields``
не добавляет поля), если ``key`` пустой — так дев/тестовое окружение без
настроенного ``BUS_SIGNING_KEY`` продолжает работать как раньше. В проде
пустой ключ отклоняется на старте (см. ``bootstrap/safety.py``).
"""

from __future__ import annotations

import hashlib
import hmac
import time

# Окно допустимого расхождения времени между отправителем и получателем
# (секунды) — защита от replay старого, но валидно подписанного сообщения.
DEFAULT_MAX_SKEW_SEC = 300


def _canonical(fields: dict) -> bytes:
    """Каноническая строка полей (без ``sig``), отсортированных по имени."""
    items = sorted((str(k), str(v)) for k, v in fields.items() if k != "sig")
    return "\x1f".join(f"{k}={v}" for k, v in items).encode("utf-8")


def sign_fields(key: str, fields: dict) -> dict:
    """Вернуть копию ``fields`` с добавленными ``ts``+``sig``.

    Если ``key`` пуст — подпись отключена, возвращает ``fields`` без изменений
    (обратная совместимость для дев/тестовых окружений без настроенного ключа).
    """
    if not key:
        return dict(fields)
    body = dict(fields)
    body["ts"] = str(int(time.time()))
    body["sig"] = hmac.new(key.encode("utf-8"), _canonical(body), hashlib.sha256).hexdigest()
    return body


def verify_fields(
    key: str, fields: dict, max_skew: int = DEFAULT_MAX_SKEW_SEC
) -> bool:
    """Проверить подпись и окно времени сообщения шины.

    Если ``key`` пуст — проверка отключена (см. docstring модуля), возвращает
    ``True`` без сверки — предполагается, что подписи и не было.
    """
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
