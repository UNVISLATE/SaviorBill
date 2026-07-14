import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from lifespan import lifespan
from utils.config import AppConfig, APP_NAME, APP_VERSION
from utils.telemetry import install_access_log_filter, setup_observability

settings = AppConfig()


logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
)
install_access_log_filter()


DESCRIPTION = (
    "**SaviorBill** is an event-driven billing service.\n\n"
    f"Media uploads, conversion, and file delivery are handled by **mediaworker**. "
    f"Its OpenAPI docs are available at [{settings.media_docs_url}]({settings.media_docs_url})."
    if settings.DOCS_ENABLED
    else "**SaviorBill** is an event-driven billing service."
)

TAGS_META = [
    {"name": "auth", "description": "Registration, login, JWT tokens, logout."},
    {"name": "oauth", "description": "Sign-in via external OAuth providers."},
    {"name": "catalog", "description": "Public service catalog and catalog tree."},
    {
        "name": "user",
        "description": "User profile, services, payments, and connections.",
    },
    {
        "name": "promocodes",
        "description": "Promo code redemption.",
    },
    {"name": "callback", "description": "Payment and OAuth callbacks."},
    {"name": "media", "description": "Media upload and processing status."},
    {"name": "admin: me", "description": "Current admin profile."},
    {"name": "admin: users", "description": "User list and editing."},
    {"name": "admin: roles", "description": "Roles and RBAC permissions."},
    {"name": "admin: services", "description": "Catalog service management."},
    {"name": "admin: catalogs", "description": "Service catalog management."},
    {"name": "admin: orders", "description": "Issued services and manual delivery."},
    {"name": "admin: purchases", "description": "Payments and providers."},
    {"name": "admin: promo", "description": "Promo catalogs and code issuance."},
    {"name": "admin: oauth", "description": "OAuth provider management."},
    {"name": "admin: lua", "description": "Lua script upload and editing."},
    {"name": "admin: email", "description": "Email templates."},
    {
        "name": "admin: triggers",
        "description": "Triggers: event to action.",
    },
    {"name": "admin: audit", "description": "Financial and admin audit log."},
    {
        "name": "admin: analytics",
        "description": "Basic and advanced analytics.",
    },
]

app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description=DESCRIPTION,
    openapi_tags=TAGS_META,
    lifespan=lifespan,
    # Вся HTTP-поверхность billing (включая служебные /health и доку) живёт
    # под префиксом /api — чтобы на одном домене можно было отдавать
    # admin/client UI на "/" без риска пересечения путей со статикой SPA.
    docs_url="/api/docs" if settings.DOCS_ENABLED else None,
    redoc_url="/api/redoc" if settings.DOCS_ENABLED else None,
    openapi_url="/api/openapi.json" if settings.DOCS_ENABLED else None,
)

# Метрики Prometheus + трейсинг OpenTelemetry (по флагам METRICS_ENABLED/OTEL_ENABLED).
setup_observability(app, settings, APP_NAME, APP_VERSION)

# CORS — нужен, только если admin/client UI обращается к billing с другого
# домена/порта через fetch()/XHR. Пусто по умолчанию -> middleware не
# подключается вовсе (нулевое изменение поведения для однодоменных деплоев).
if settings.cors_origins_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Доверять X-Forwarded-For/-Proto только если явно сконфигурирован список
# реверс-прокси — иначе `request.client.host` (реальный TCP-peer) остаётся
# единственным источником IP клиента (см. dependencies/ratelimit.py,
# IMPLEMENTATION_PLAN §10). Без этого небезопасный дефолт "доверяем всегда"
# позволял бы обойти rate-limit по IP подделкой заголовка напрямую.
if settings.trusted_proxies_list:
    app.add_middleware(
        ProxyHeadersMiddleware, trusted_hosts=settings.trusted_proxies_list
    )

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=settings.HOST, port=settings.PORT)
