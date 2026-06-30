"""Ужесточение прав файлов секретов при первом запуске."""

from __future__ import annotations

import logging
import os
import stat
from pathlib import Path

from utils.config import AppConfig

log = logging.getLogger("saviorbill.init")

# Желаемые права файла секрета: владелец r/w, остальные — ничего.
_KEY_MODE = stat.S_IRUSR | stat.S_IWUSR  # 0o600


def _secret_files(cfg: AppConfig) -> list[Path]:
    """Список путей файлов секретов, релевантных файловому бэкенду.

    :arg cfg: конфигурация приложения.
    :return: пути к файлам секретов.
    """
    candidates = [
        cfg.SECRETS_KEY_PATH,
        cfg.JWT_SECRET_FILE,
        cfg.LUA_SERVICE_TOKEN_FILE,
        cfg.DB_PASS_FILE,
        cfg.SMTP_PASS_FILE,
        cfg.S3_SECRET_FILE,
    ]
    return [Path(p) for p in candidates if p]


def harden_secret(cfg: AppConfig) -> None:
    """Ужесточить права файлов секретов (POSIX).

    :arg cfg: конфигурация приложения.
    """
    if os.name != "posix":
        log.info("не-POSIX ОС: права файлов секретов не меняются")
        return

    for path in _secret_files(cfg):
        if not path.exists():
            continue
        try:
            os.chmod(path, _KEY_MODE)
            log.info("права файла секрета %s ужесточены до 0o600", path)
        except OSError as exc:  # pragma: no cover - зависит от ФС/ОС
            log.warning("не удалось изменить права файла секрета %s: %s", path, exc)


__all__ = ["harden_secret"]
