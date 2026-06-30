from contextlib import asynccontextmanager

from fastapi import FastAPI

from dependencies.db import create_db_engine, create_db_sessionmaker
from dependencies.valkey import create_valkey_client
from utils.config import AppConfig
from utils.bootstrap import bootstrap
from utils.openapi import document_perms
from utils.sec.secrets.resolve import resolve_secrets

from api import api_router


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
    _prepare_storage(config)
    app.state.settings = config

    app.state.db_engine = create_db_engine(config.db_url)
    app.state.db_sessionmaker = create_db_sessionmaker(app.state.db_engine)
    app.state.valkey = create_valkey_client(config.valkey_url)

    # Первичная инициализация: owner-роль/пользователь, сид настроек SMTP.
    await bootstrap(config, app.state.db_sessionmaker, app.state.valkey)

    app.include_router(api_router)
    # Роуты добавлены — задокументировать требуемые права в OpenAPI.
    document_perms(app)

    try:
        yield
    finally:
        await app.state.valkey.aclose()
        await app.state.db_engine.dispose()
