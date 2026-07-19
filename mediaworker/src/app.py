from __future__ import annotations

import os
from pathlib import Path

from utils.config import Config
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from api import router
from lifespan import lifespan
from utils.telemetry import install_access_log_filter, setup_observability
from utils.version import resolve_app_version

_cfg = Config()

# Корень приложения: в Docker-образе — /app (VERSION лежит рядом), в
# локальном чек-ауте — mediaworker/ (родитель src/, .git — на уровень выше).
_BASE_DIR = Path(__file__).resolve().parents[1]

APP_NAME = os.environ.get("APP_NAME", "saviormedia")
APP_VERSION = resolve_app_version(_BASE_DIR)

install_access_log_filter()

app = FastAPI(
    title=f"SaviorBill - {APP_NAME}",
    version=APP_VERSION,
    lifespan=lifespan,
    # Вся HTTP-поверхность mediaworker (включая /health и доку) живёт под
    # /api/media — чтобы billing + mediaworker + admin/client UI можно было
    # при желании уместить на одном домене без пересечения путей (по
    # умолчанию всё равно разносятся по отдельным (под)доменам, см. Caddyfile).
    docs_url="/api/media/docs" if _cfg.docs_enabled else None,
    redoc_url="/api/media/redoc" if _cfg.docs_enabled else None,
    openapi_url="/api/media/openapi.json" if _cfg.docs_enabled else None,
)

# Метрики Prometheus + трейсинг OpenTelemetry (по флагам METRICS_ENABLED/OTEL_ENABLED).
setup_observability(app, _cfg, APP_NAME, APP_VERSION)

# CORS — нужен для JS fetch()/XHR (загрузка/статус) с другого домена, чем
# mediaworker; отдача самих файлов через <img>/<video> CORS не требует.
# Пусто по умолчанию -> middleware не подключается (нулевое изменение
# поведения для однодоменных/same-origin деплоев).
if _cfg.cors_origins_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cfg.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Доверять X-Forwarded-For/-Proto только если явно сконфигурирован список
# реверс-прокси — иначе `request.client.host` (реальный TCP-peer) остаётся
# единственным источником IP клиента (см. utils/authctx.py::client_ip).
if _cfg.trusted_proxies_list:
    app.add_middleware(
        ProxyHeadersMiddleware, trusted_hosts=_cfg.trusted_proxies_list
    )

app.include_router(router)

__all__ = ["app"]


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=_cfg.MEDIA_HOST, port=_cfg.MEDIA_PORT)
