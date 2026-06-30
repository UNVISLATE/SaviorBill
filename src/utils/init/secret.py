"""Ужесточение прав файла секретного ключа при первом запуске."""

from __future__ import annotations

import logging
import os
import stat

from utils.config import AppConfig

log = logging.getLogger("saviorbill.init")

# Желаемые права файла ключа: владелец r/w, остальные — ничего.
_KEY_MODE = stat.S_IRUSR | stat.S_IWUSR  # 0o600


def harden_secret(cfg: AppConfig) -> None:
    """Ужесточить права файла секретного ключа (POSIX)."""
    path = cfg.secret_key_file
    if not path.exists():
        log.warning("файл ключа %s отсутствует — пропуск ужесточения прав", path)
        return

    if os.name != "posix":
        log.info("не-POSIX ОС: права файла ключа %s не меняются", path)
        return

    try:
        os.chmod(path, _KEY_MODE)
        log.info("права файла ключа %s ужесточены до 0o600", path)
    except OSError as exc:  # pragma: no cover - зависит от ФС/ОС
        log.warning("не удалось изменить права файла ключа %s: %s", path, exc)


__all__ = ["harden_secret"]
