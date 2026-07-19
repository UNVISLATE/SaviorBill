from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

import valkey.asyncio as valkey
from fastapi import FastAPI

from utils.config import Config
from utils.db import DB
from utils.proclog import ProcLog
from utils.settings import SettingsResolver
from utils.storage import Storage
from utils.task_log import TaskLog
from utils.telemetry import instrument_valkey
from utils.worker import Worker

log = logging.getLogger("saviorbill.media")


async def _supervised(name: str, coro_factory) -> None:
    """Перезапускать фоновую задачу при непойманном исключении.

    Раньше ``worker.run()``/``reclaim_loop()`` создавались как одноразовый
    ``asyncio.create_task`` без надзора: любое необработанное исключение
    (например, временный обрыв соединения с Valkey) тихо останавливало цикл
    навсегда — mediaworker выглядел "живым" (HTTP отвечает), но перестал бы
    забирать задачи из стрима. Обёртка логирует сбой и перезапускает корутину
    с небольшой паузой, вместо того чтобы дать процессу "притвориться" рабочим.
    """
    while True:
        try:
            await coro_factory()
            return  # штатное завершение (отмена/остановка) — не перезапускаем
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            log.exception("[mediaworker] задача %s упала, перезапуск через 2с", name)
            await asyncio.sleep(2)


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = Config()
    if not (cfg.BUS_SIGNING_KEY or "").strip():
        # без общего секрета media:tasks/media:results не
        # подписываются — billing (см. bootstrap/safety.py) откажется
        # стартовать в проде без BUS_SIGNING_KEY, здесь — только предупреждение
        # в лог, т.к. у mediaworker нет собственного понятия DEBUG/prod-режима.
        log.warning(
            "[mediaworker] BUS_SIGNING_KEY не задан — media:tasks/media:results "
            "не подписываются, шина не защищена от подмены сообщений"
        )
    vk = valkey.from_url(cfg.valkey_url, decode_responses=True)
    instrument_valkey(vk, cfg)
    storage = Storage(cfg)
    db = DB(cfg.db_dsn)
    await db.connect()
    settings = SettingsResolver(cfg, vk, db)
    task_log = TaskLog(
        vk,
        max_len=cfg.tasklog_maxlen,
        ttl=cfg.tasklog_ttl,
        job_events_stream=cfg.MEDIA_JOB_EVENTS_STREAM,
        job_events_maxlen=cfg.MEDIA_JOB_EVENTS_MAXLEN,
        signing_key=cfg.BUS_SIGNING_KEY,
    )
    proc_log = ProcLog(vk, max_jobs=cfg.proclog_max_jobs, ttl=cfg.proclog_ttl)
    worker = Worker(cfg, vk, storage, settings, task_log, proc_log)

    app.state.cfg = cfg
    app.state.vk = vk
    app.state.storage = storage
    app.state.db = db
    app.state.settings = settings
    app.state.task_log = task_log
    app.state.proc_log = proc_log

    task = asyncio.create_task(_supervised("worker.run", worker.run))
    reclaim_task = asyncio.create_task(_supervised("worker.reclaim_loop", worker.reclaim_loop))
    log.info(
        "[mediaworker] %s -> %s backend=%s stream=%s",
        cfg.consumer,
        cfg.valkey_url,
        cfg.backend,
        cfg.task_stream,
    )
    try:
        yield
    finally:
        task.cancel()
        reclaim_task.cancel()
        for t in (task, reclaim_task):
            try:
                await t
            except asyncio.CancelledError:
                pass
        await db.close()
        await vk.aclose()


__all__ = ["lifespan"]
