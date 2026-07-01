"""Сидинг базовых lua-шаблонов при первом запуске.

Регистрирует поставляемые с образом эталонные шаблоны провайдеров (ЮKassa,
Platega и т.п.) в таблице ``lua_scripts`` по нейтральным слагам. Запись ссылается
на уже лежащий в ``LUA_SCRIPTS_DIR`` файл (без копирования) — единый источник.
Демо-скрипты для тестов сюда не входят.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from enums import ScriptKind
from models.system_scripts import SystemScriptsModel
from utils.config import AppConfig

log = logging.getLogger("saviorbill.init")

# Базовые шаблоны: slug -> (имя, вид, относительный путь, описание).
_BASE: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "base_yookassa_init",
        "ЮKassa · инициализация платежа",
        ScriptKind.PAYMENT,
        "payments/yookassa_init.lua",
        "Эталонный init-скрипт ЮKassa (создание платежа, ссылка на оплату).",
    ),
    (
        "base_yookassa_callback",
        "ЮKassa · колбэк",
        ScriptKind.PAYMENT,
        "payments/yookassa_callback.lua",
        "Эталонный callback-скрипт ЮKassa (проверка/перепроверка статуса).",
    ),
    (
        "base_platega_init",
        "Platega · инициализация платежа",
        ScriptKind.PAYMENT,
        "payments/platega_init.lua",
        "Эталонный init-скрипт Platega (создание транзакции, ссылка на оплату).",
    ),
    (
        "base_platega_callback",
        "Platega · колбэк",
        ScriptKind.PAYMENT,
        "payments/platega_callback.lua",
        "Эталонный callback-скрипт Platega (проверка/перепроверка статуса).",
    ),
    (
        "base_service_lua",
        "Базовый шаблон услуги (action-driven)",
        ScriptKind.SERVICE,
        "base/service_lua.lua",
        "Эталонный сервисный шаблон: create/renew/stop/delete/freeze.",
    ),
)


async def seed_lua_scripts(session: AsyncSession, cfg: AppConfig) -> list[str]:
    """Зарегистрировать отсутствующие базовые lua-шаблоны. Идемпотентно.

    :arg session: активная сессия БД.
    :arg cfg: конфигурация (путь к папке lua-скриптов).
    :return: список созданных слагов.
    """
    scripts_dir = Path(cfg.LUA_SCRIPTS_DIR)
    created: list[str] = []
    for slug, name, kind, rel, desc in _BASE:
        exists = await session.scalar(
            select(SystemScriptsModel.id).where(SystemScriptsModel.slug == slug)
        )
        if exists is not None:
            continue
        source = scripts_dir / rel
        if not source.exists():
            log.warning("базовый шаблон отсутствует на диске: %s", rel)
            continue
        code = source.read_text(encoding="utf-8")
        session.add(
            SystemScriptsModel(
                slug=slug,
                name=name,
                kind=kind,
                filename=rel,
                sha256=hashlib.sha256(code.encode()).hexdigest(),
                description=desc,
            )
        )
        created.append(slug)
    if created:
        log.info("зарегистрированы базовые lua-шаблоны: %s", ", ".join(created))
    return created


__all__ = ["seed_lua_scripts"]
