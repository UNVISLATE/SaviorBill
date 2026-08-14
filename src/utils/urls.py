"""Валидация URL, которые эхом уходят наружу (open-redirect защита)."""

from __future__ import annotations

from urllib.parse import urlsplit


def is_safe_return_url(url: str, allowed_origins: list[str]) -> bool:
    """Разрешить только относительные пути проекта или allowlist-origin'ы.

    Используется для ``return_url`` в платежах — провайдер оплаты доверенный
    и подставит его как есть в редирект после оплаты, поэтому произвольный
    абсолютный URL здесь означает open redirect через доверенный сервис
    (см. AUDIT.md §2.5).

    :arg url: значение, присланное клиентом.
    :arg allowed_origins: allowlist абсолютных origin'ов (схема+хост[:порт]),
        например ``CORS_ORIGINS`` из конфигурации.
    :return: ``True``, если url — безопасный относительный путь (не
        protocol-relative ``//host/...``) либо абсолютный URL с origin из
        allowlist.
    """
    if not url:
        return False
    parts = urlsplit(url)
    if not parts.scheme and not parts.netloc:
        # Относительный путь. "//host/..." парсится как netloc без scheme —
        # это protocol-relative URL (браузер уйдёт на произвольный хост),
        # должен начинаться строго с одного "/".
        return url.startswith("/") and not url.startswith("//")
    origin = f"{parts.scheme}://{parts.netloc}"
    return origin in allowed_origins


__all__ = ["is_safe_return_url"]
