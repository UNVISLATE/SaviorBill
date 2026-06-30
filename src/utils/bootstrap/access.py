"""Проверки доступа/прав окружения процесса (на каждом запуске)."""

from __future__ import annotations

import logging
import os
import stat

from dependencies.settings import SystemSettingsMngr
from utils.config import AppConfig

log = logging.getLogger("saviorbill.bootstrap")


def _world_writable(path) -> bool:
    """Доступен ли путь на запись «группе» или «другим»."""
    mode = path.stat().st_mode
    return bool(mode & (stat.S_IWGRP | stat.S_IWOTH))


def _key_too_open(path) -> bool:
    """Имеет ли файл ключа доступ кому-либо кроме владельца."""
    mode = path.stat().st_mode
    return bool(mode & (stat.S_IRWXG | stat.S_IRWXO))


async def check_access(mngr: SystemSettingsMngr, cfg: AppConfig) -> bool:
    """Проверить права процесса и файлов ``data/*``.

    Возвращает ``True``, если обнаружены небезопасные права (insecure).
    """
    insecure = False

    if os.name != "posix":
        log.info("не-POSIX ОС: проверки прав файлов/пользователя пропущены")
        await mngr.set("system.fs_insecure", "0", is_secret=False)
        return False

    # 1. Процесс не должен быть root.
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        insecure = True
        log.warning("биллинг запущен от root — это небезопасно")

    # 2. Файл секретного ключа — только владельцу.
    key_file = cfg.secret_key_file
    if key_file.exists() and _key_too_open(key_file):
        insecure = True
        log.warning(
            "файл ключа %s доступен не только владельцу (ожидается 0o600/0o400)",
            key_file,
        )

    # 3. Прочие файлы data/* не должны быть world/group-writable.
    data_dir = cfg.data_path
    if data_dir.exists():
        for entry in data_dir.rglob("*"):
            if entry == key_file or not entry.is_file():
                continue
            if _world_writable(entry):
                insecure = True
                log.warning("файл %s доступен на запись группе/другим", entry)

    await mngr.set("system.fs_insecure", "1" if insecure else "0", is_secret=False)
    if not insecure:
        log.info("проверка прав ФС/процесса: OK")
    return insecure


__all__ = ["check_access"]
