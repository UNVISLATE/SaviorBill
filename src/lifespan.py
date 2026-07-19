from contextlib import asynccontextmanager

from fastapi import FastAPI

from dependencies.db import create_db_engine, create_db_sessionmaker
from dependencies.valkey import create_valkey_client
from services.billing_loop import BillingLoop
from services.media_results import MediaResults
from services.media_job_events import MediaJobEvents
from core.config import AppConfig
from bootstrap import bootstrap
from bootstrap.init import init_system
from bootstrap.safety import check_dangerous_defaults
from utils.openapi import document_perms
from security.sec.secrets.resolve import resolve_secrets
from telemetry.task_log import TaskLog
from telemetry.otel import instrument_sqlalchemy, instrument_valkey
from telemetry.lua_metrics import LuaMetricsCollector

from api import api_router
from apiws import apiws_router


def _prepare_storage(config: AppConfig) -> None:
    """Создать монтируемые папки и разрешить секреты через выбранный бэкенд."""
    config.keys_dir.mkdir(parents=True, exist_ok=True)
    if config.STORAGE_BACKEND == "fs":
        config.uploads_dir.mkdir(parents=True, exist_ok=True)
    # Все секреты — внешние ресурсы (файлы/менеджер). Создаём при отсутствии.
    resolve_secrets(config)


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = AppConfig()
    # Прежде чем трогать БД/Valkey — убедиться, что не остались опасные
    # плейсхолдеры из .env.example (см. bootstrap/safety.py).
    check_dangerous_defaults(config)
    _prepare_storage(config)
    app.state.settings = config

    app.state.db_engine = create_db_engine(config.db_url)
    app.state.db_sessionmaker = create_db_sessionmaker(app.state.db_engine)
    app.state.valkey = create_valkey_client(config.valkey_url)
    app.state.task_log = TaskLog(
        app.state.valkey, max_len=config.TASKLOG_MAXLEN, ttl=config.TASKLOG_TTL
    )

    # Автоинструментация запросов к БД (no-op, если трейсинг выключен).
    instrument_sqlalchemy(app.state.db_engine, config)
    instrument_valkey(app.state.valkey, config)

    # Первичная инициализация (один раз) и per-run проверки — независимые модули.
    await init_system(config, app.state.db_sessionmaker, app.state.valkey)
    await bootstrap(config, app.state.db_sessionmaker, app.state.valkey)

    # Планировщик истечений услуг и перепроверок платежей (in-process).
    app.state.billing_loop = BillingLoop(
        app.state.db_engine,
        app.state.db_sessionmaker,
        app.state.valkey,
        config,
        app.state.task_log,
    )
    await app.state.billing_loop.start()

    # Консьюмер результатов конвертации медиа (mediaworker -> billing пишет в БД).
    app.state.media_results = MediaResults(
        app.state.db_sessionmaker,
        app.state.valkey,
        config,
    )
    await app.state.media_results.start()

    # Консьюмер переходов статуса медиа-задач -> worker_jobs (см. models/worker_jobs.py).
    app.state.media_job_events = MediaJobEvents(
        app.state.db_sessionmaker,
        app.state.valkey,
        config,
    )
    await app.state.media_job_events.start()

    # Переэкспорт метрик LuaWorker (push в Valkey -> Prometheus Gauge, см.
    # telemetry/lua_metrics.py).
    app.state.lua_metrics = LuaMetricsCollector(app.state.valkey, config)
    await app.state.lua_metrics.start()

    app.include_router(api_router)
    app.include_router(apiws_router)
    # Роуты добавлены — задокументировать требуемые права в OpenAPI.
    document_perms(app)

    try:
        yield
    finally:
        await app.state.lua_metrics.stop()
        await app.state.media_job_events.stop()
        await app.state.media_results.stop()
        await app.state.billing_loop.stop()
        await app.state.valkey.aclose()
        await app.state.db_engine.dispose()
