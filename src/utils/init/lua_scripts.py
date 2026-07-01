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

# Базовые шаблоны: slug -> (имя, вид, относительный путь, действия, описание).
_BASE: tuple[tuple[str, str, str, str, tuple[str, ...], str], ...] = (
    (
        "base_yookassa_payment",
        "ЮKassa · платёж (единый скрипт)",
        ScriptKind.PAYMENT,
        "payments/yookassa_payment.lua",
        ("create", "callback", "check", "refund"),
        "Эталонный action-driven скрипт ЮKassa (create/callback/check/refund).",
    ),
    (
        "base_platega_payment",
        "Platega · платёж (единый скрипт)",
        ScriptKind.PAYMENT,
        "payments/platega_payment.lua",
        ("create", "callback", "check", "refund"),
        "Эталонный action-driven скрипт Platega (create/callback/check/refund).",
    ),
    (
        "base_service_lua",
        "Базовый шаблон услуги (action-driven)",
        ScriptKind.SERVICE,
        "base/service_lua.lua",
        ("create", "renew", "stop", "delete", "freeze"),
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
    for slug, name, kind, rel, actions, desc in _BASE:
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
                actions=list(actions),
            )
        )
        created.append(slug)
    if created:
        log.info("зарегистрированы базовые lua-шаблоны: %s", ", ".join(created))
    return created


__all__ = ["seed_lua_scripts"]
