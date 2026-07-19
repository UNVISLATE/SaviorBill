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
from utils.worker import Worker

log = logging.getLogger("saviorbill.media")


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = Config()
    if not (cfg.BUS_SIGNING_KEY or "").strip():
        # См. AUDIT.md H1: без общего секрета media:tasks/media:results не
        # подписываются — billing (см. bootstrap/safety.py) откажется
        # стартовать в проде без BUS_SIGNING_KEY, здесь — только предупреждение
        # в лог, т.к. у mediaworker нет собственного понятия DEBUG/prod-режима.
        log.warning(
            "[mediaworker] BUS_SIGNING_KEY не задан — media:tasks/media:results "
            "не подписываются, шина не защищена от подмены сообщений (AUDIT.md H1)"
        )
    vk = valkey.from_url(cfg.valkey_url, decode_responses=True)
    storage = Storage(cfg)
    db = DB(cfg.db_dsn)
    await db.connect()
    settings = SettingsResolver(cfg, vk, db)
    task_log = TaskLog(vk, max_len=cfg.tasklog_maxlen, ttl=cfg.tasklog_ttl)
    proc_log = ProcLog(vk, max_jobs=cfg.proclog_max_jobs, ttl=cfg.proclog_ttl)
    worker = Worker(cfg, vk, storage, settings, task_log, proc_log)

    app.state.cfg = cfg
    app.state.vk = vk
    app.state.storage = storage
    app.state.db = db
    app.state.settings = settings
    app.state.task_log = task_log
    app.state.proc_log = proc_log

    task = asyncio.create_task(worker.run())
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
        try:
            await task
        except asyncio.CancelledError:
            pass
        await db.close()
        await vk.aclose()


__all__ = ["lifespan"]
