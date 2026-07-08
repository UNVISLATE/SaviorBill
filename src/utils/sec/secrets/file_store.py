"""Файловое хранилище секретов (бэкенд по умолчанию).

Каждый секрет — отдельный файл. ENV задаёт путь, значение генерируется/читается
из файла. На POSIX файлы создаются с правами 0600.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

from .base import SecretStore


class FileSecretStore(SecretStore):
    """Секреты как файлы в монтируемой папке данных."""

    name = "file"

    def __init__(self, paths: dict[str, Path]) -> None:
        """:arg paths: отображение логического имени секрета на путь к файлу."""
        self.paths = {k: Path(v) for k, v in paths.items()}

    def get(self, key: str) -> str | None:
        path = self.paths.get(key)
        if path is None or not path.exists():
            return None
        value = path.read_text(encoding="utf-8").strip()
        return value or None

    def put(self, key: str, value: str) -> None:
        path = self.paths.get(key)
        if path is None:
            raise KeyError(f"the file path for the secret {key!r} is not specified")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")
        if os.name == "posix":
            try:
                os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)  # 0o600
            except OSError:  # pragma: no cover — зависит от ФС
                pass


__all__ = ["FileSecretStore"]
