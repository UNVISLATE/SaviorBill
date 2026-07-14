"""Определение версии приложения в рантайме.

Приоритет источников:
1. Файл ``VERSION`` рядом с корнем приложения (``/app/VERSION`` в
   Docker-образе) — записывается один раз в CI перед сборкой образа
   (``setuptools_scm.get_version()`` на чек-ауте релизного тега), без
   зависимости от ``.git``/``setuptools_scm`` в рантайме контейнера.
2. Если файла нет, но есть ``.git`` (локальный дев-чекаут) — версия
   вычисляется "на лету" через ``setuptools_scm.get_version()`` при каждом
   старте процесса (например ``0.3.1.dev6+g9f1c2ab`` через несколько
   коммитов после тега ``v0.3.1``).
3. Если недоступно ни то, ни другое (например, склонировали без тегов,
   ``setuptools_scm`` не установлен) — статичный fallback.
"""

from __future__ import annotations

from pathlib import Path

FALLBACK_VERSION = "0.0.0-dev"


def resolve_app_version(base_dir: Path) -> str:
    """Версия приложения: baked ``VERSION`` (прод-образ) > live git (дев) > fallback.

    :arg base_dir: корень приложения (в Docker-образе — ``/app``, в
        локальном чек-ауте — корень репозитория), где лежит ``VERSION``
        и/или ``.git``.
    """
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
