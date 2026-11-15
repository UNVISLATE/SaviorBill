"""Определение версии приложения в рантайме."""

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
