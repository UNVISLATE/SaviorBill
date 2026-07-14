from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

import valkey.asyncio as valkey
from fastapi import FastAPI

from utils.config import Config
from utils.db import DB
from utils.settings import SettingsResolver
from utils.storage import Storage
from utils.worker import Worker

log = logging.getLogger("saviorbill.media")


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = Config()
    vk = valkey.from_url(cfg.valkey_url, decode_responses=True)
    storage = Storage(cfg)
    db = DB(cfg.db_dsn)
    await db.connect()
    worker = Worker(cfg, vk, storage)

    app.state.cfg = cfg
    app.state.vk = vk
    app.state.storage = storage
    app.state.db = db
    app.state.settings = SettingsResolver(cfg, vk, db)

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
