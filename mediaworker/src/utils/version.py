"""Определение версии приложения в рантайме (см. upd_plan.md, часть 3).

Та же логика, что и в ``billing`` (``src/utils/version.py``) — сознательно
продублирована здесь: mediaworker — отдельный процесс/образ со своим
корнем (``/app``), общий пакет между сервисами не заводим ради одной
маленькой функции.

Приоритет источников:
1. Файл ``VERSION`` рядом с корнем приложения (``/app/VERSION`` в
   Docker-образе), записанный один раз в CI перед сборкой (см. upd_plan.md).
2. Если файла нет, но есть ``.git`` (локальный дев-чекаут) — версия
   вычисляется "на лету" через ``setuptools_scm.get_version()``.
3. Иначе — статичный fallback.
"""

from __future__ import annotations

from pathlib import Path

FALLBACK_VERSION = "0.0.0-dev"


def resolve_app_version(base_dir: Path) -> str:
    """Версия приложения: baked ``VERSION`` (прод-образ) > live git (дев) > fallback."""
    version_file = base_dir / "VERSION"
    if version_file.is_file():
        text = version_file.read_text(encoding="utf-8").strip()
        if text:
            return text

    try:
        from setuptools_scm import get_version

        return get_version(root=str(base_dir), fallback_version=FALLBACK_VERSION)
    except Exception:
        return FALLBACK_VERSION


__all__ = ["resolve_app_version", "FALLBACK_VERSION"]
