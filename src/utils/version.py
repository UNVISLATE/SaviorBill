"""Определение версии приложения в рантайме."""

from __future__ import annotations

from pathlib import Path

FALLBACK_VERSION = "0.0.0-dev"


def saviorbill_version_scheme(version: object) -> str:
    """Схема версионирования SaviorBill:
    - Точный тег (релиз): '0.2.2'
    - Коммиты после тега: '0.2.2.dev<distance>'
    - Незакоммиченные изменения на теге: '0.2.2.dev0'
    Никогда не перескакивает на следующий номер версии до создания тега.
    """
    exact = getattr(version, "exact", False)
    dirty = getattr(version, "dirty", False)
    distance = getattr(version, "distance", None)
    tag = str(getattr(version, "tag", "0.0.0"))

    if exact and not dirty:
        return tag
    if distance:
        return f"{tag}.dev{distance}"
    if dirty:
        return f"{tag}.dev0"
    return tag


def resolve_app_version(base_dir: Path) -> str:
    """Версия приложения: baked ``VERSION`` (прод-образ) > live git (дев) > fallback.

    :arg base_dir: корень приложения (в Docker-образе — ``/app``, в
        локальном чек-ауте — корень репозитория), где лежит ``VERSION``
        и/или ``.git``.
    """
    version_file = base_dir / "VERSION"
    if version_file.is_file():
        text = version_file.read_text(encoding="utf-8").strip()
        if text and text != FALLBACK_VERSION:
            return text

    try:
        from setuptools_scm import get_version

        return get_version(
            root=str(base_dir),
            version_scheme=saviorbill_version_scheme,
            local_scheme="node-and-date",
            fallback_version=FALLBACK_VERSION,
        )
    except Exception:
        return FALLBACK_VERSION


__all__ = ["resolve_app_version", "saviorbill_version_scheme", "FALLBACK_VERSION"]
